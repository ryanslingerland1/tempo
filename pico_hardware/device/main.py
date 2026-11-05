"""Tempo USB-tethered MicroPython firmware. Copy with lcd.py to the Pico."""
import sys
import select
import json
import time
import gc
from lcd import Display

THEMES = ('ORP', 'ORP Night', 'Classic', 'Night')
HOLD_MS = 500
DOUBLE_MS = 300


class Link:
    def __init__(self):
        self.poll = select.poll()
        self.poll.register(sys.stdin, select.POLLIN)
        self.buffer = ''
        self.events = []
        self.sequence = 0
        self.last_seen = time.ticks_ms()
        self.connected = False

    def receive(self):
        if not self.poll.poll(0):
            return None
        char = sys.stdin.read(1)
        if not char:
            return None
        if char != '\n':
            if len(self.buffer) < 16384:
                self.buffer += char
            else:
                self.buffer = ''
            return None
        line, self.buffer = self.buffer, ''
        try:
            message = json.loads(line)
        except ValueError:
            return None
        if not isinstance(message, dict):
            return None
        self.last_seen = time.ticks_ms()
        if 'key' in message or message.get('disconnect'):
            if len(self.events) < 40:
                self.events.append(message)
        return message

    def rpc(self, op, **args):
        self.sequence += 1
        request_id = self.sequence
        print(json.dumps({'id': request_id, 'op': op, 'args': args}))
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < 4000:
            message = self.receive()
            if message and message.get('id') == request_id:
                if not message.get('ok'):
                    raise ValueError(message.get('error', 'Mac helper error'))
                self.connected = True
                return message['data']
            if not self.poll.poll(0):
                time.sleep_ms(1)
        self.connected = False
        raise OSError('Mac helper did not respond')


class Tempo:
    def __init__(self):
        self.lcd = Display()
        self.link = Link()
        self.screen = 'waiting'
        self.running = False
        self.book = None
        self.held = {}
        self.pending_center = None
        self.index = 0
        self.words_read = 0
        self.seconds_read = 0
        self.last_save = time.ticks_ms()
        self.settings = {}
        self.chunk = []
        self.chunk_start = 0
        self.lcd.menu('Tempo Pico', ['Waiting for Mac helper...'], 0)

    def home(self):
        self.running = False
        self.pending_center = None
        self.screen = 'home'
        self.index = 0
        self.lcd.theme(False)
        self.render()

    def save(self):
        if self.book and self.link.connected:
            self.link.rpc('save', position=self.position, wpm=self.wpm, theme=self.theme)
        if (self.words_read or self.seconds_read) and self.link.connected:
            self.link.rpc('stats', words=self.words_read, seconds=self.seconds_read)
            self.words_read = 0
            self.seconds_read = 0
        self.last_save = time.ticks_ms()

    def rows(self):
        if self.screen == 'home':
            return ['Books', 'Flashcards', 'Stats', 'Settings']
        if self.screen == 'library':
            return [entry['name'] + (' /' if entry['dir'] else '') for entry in self.entries]
        if self.screen == 'chapters':
            return [entry[1] for entry in self.entries]
        if self.screen == 'settings':
            return ['Default speed: %s WPM' % self.settings.get('default_wpm', 300),
                    'Pause at chapters: ' + ('On' if self.settings.get('chapter_auto_pause', False) else 'Off'),
                    'Sleep timer: %s min' % self.settings.get('sleep_timer', 0)]
        if self.screen == 'deck_options':
            return ['Resume deck', 'Reset deck', 'Cancel']
        if self.screen == 'reset':
            return ['Cancel', 'Reset deck']
        return []

    def render(self):
        if self.screen == 'read':
            entry = self.current()
            status = '%s | %d WPM | %d/%d' % (
                'Reading' if self.running else 'Paused', self.wpm, self.position + 1, self.book['total'])
            if self.position == self.book['total'] - 1 and not self.running:
                status = 'Last word | ' + status
            self.lcd.word(entry[0], status, self.theme.startswith('ORP'), self.context() if self.seeking else '')
        elif self.screen == 'cards':
            text = self.card['back'] if self.flipped else self.card['front']
            # Long cards have pages. Double-center advances a page.
            lines = []
            for paragraph in text.splitlines() or ['']:
                line = ''
                for word in paragraph.split():
                    for offset in range(0, len(word), 50):
                        part = word[offset:offset + 50]
                        if len(line) + len(part) + 1 > 50:
                            lines.append(line)
                            line = part
                        else:
                            line = (line + ' ' + part).strip()
                lines.append(line)
            self.card_pages = max(1, (len(lines) + 4) // 5)
            self.card_page %= self.card_pages
            self.lcd.menu('%s | %d remaining | %d/%d' % (
                'Back' if self.flipped else 'Front', self.card['remaining'], self.card_page + 1, self.card_pages),
                lines[self.card_page * 5:self.card_page * 5 + 5], -1,
                'A keep | S flip (double: page) | D known')
        else:
            title = {'home': 'Tempo', 'library': 'Library', 'chapters': 'Chapters',
                     'settings': 'Settings', 'deck_options': 'Deck options', 'reset': 'Reset this deck?'}.get(self.screen, 'Tempo')
            if self.screen == 'library':
                title = 'Books' if self.category == 'books' else 'Flashcards'
            if self.screen in ('library', 'chapters'):
                title += ' %d/%d' % (self.index + 1 if self.total else 0, self.total)
            self.lcd.menu(title, self.rows() or ['(Empty)'],
                          self.index - self.page_start if self.screen in ('library', 'chapters') else self.index,
                          'Hold S: back | A / D: move | S: select')

    def library(self, category, folder=''):
        self.category, self.folder = category, folder
        self.screen = 'library'
        self.index = 0
        self.load_page()

    def load_page(self):
        self.page_start = (self.index // 5) * 5
        if self.screen == 'chapters':
            result = self.link.rpc('chapters', start=self.page_start)
        else:
            result = self.link.rpc('list', category=self.category, folder=self.folder, start=self.page_start)
        self.entries, self.total = result['entries'], result['total']
        self.render()

    def current(self):
        if not self.chunk_start <= self.position < self.chunk_start + len(self.chunk):
            self.chunk_start = max(0, self.position - 8)
            result = self.link.rpc('chunk', start=self.chunk_start)
            self.chunk = result['words']
            gc.collect()
        return self.chunk[self.position - self.chunk_start]

    def context(self):
        local = self.position - self.chunk_start
        return ' '.join(entry[0] for entry in self.chunk[max(0, local - 3):local + 4])[:52]

    def open_book(self, key):
        self.book = self.link.rpc('open', key=key)
        self.position = self.book['position']
        self.wpm = self.book['wpm']
        self.theme = self.book['theme'] if self.book['theme'] in THEMES else 'ORP'
        self.chunk = []
        self.screen = 'read'
        self.running = False
        self.seeking = False
        self.opened_at = time.ticks_ms()
        self.lcd.theme(self.theme in ('ORP Night', 'Night'))
        self.render()

    def pause(self):
        self.running = False
        self.pending_center = None
        self.save()
        self.render()

    def start(self):
        self.pending_center = None
        self.seeking = False
        self.running = True
        self.schedule()
        self.render()

    def schedule(self):
        self.word_delay = int(60000 / self.wpm * self.current()[1])
        self.due = time.ticks_add(time.ticks_ms(), self.word_delay)

    def tap(self, key):
        if self.screen == 'read':
            if key == 'center':
                if self.running:
                    self.pause()
                elif self.pending_center is not None:
                    self.pending_center = None
                    self.theme = THEMES[(THEMES.index(self.theme) + 1) % len(THEMES)]
                    self.lcd.theme(self.theme in ('ORP Night', 'Night'))
                    self.save()
                    self.render()
                else:
                    self.pending_center = time.ticks_ms()
            else:
                self.wpm = max(25, min(1000, self.wpm + (-25 if key == 'left' else 25)))
                if self.running:
                    self.schedule()
                else:
                    self.save()
                self.render()
            return
        if self.screen == 'cards':
            if key == 'center':
                if self.pending_center is not None:
                    self.pending_center = None
                    self.card_page += 1
                    self.render()
                else:
                    self.pending_center = time.ticks_ms()
            else:
                self.pending_center = None
                self.card = self.link.rpc('card', known=key == 'right')
                self.flipped = False
                self.card_page = 0
                self.render()
            return
        if self.screen in ('stats', 'error'):
            self.home()
            return
        if key != 'center':
            self.pending_center = None
            total = self.total if self.screen in ('library', 'chapters') else len(self.rows())
            if total:
                self.index = (self.index + (-1 if key == 'left' else 1)) % total
                if self.screen in ('library', 'chapters'):
                    if self.index // 5 != self.page_start // 5:
                        self.load_page()
                        return
            self.render()
            return
        if self.screen == 'home':
            if self.index < 2:
                self.library('books' if self.index == 0 else 'flashcards')
            elif self.index == 2:
                stats = self.link.rpc('stats')
                self.screen = 'stats'
                self.lcd.menu('Stats', ['Words read: %d' % stats['total_words_read'],
                    'Reading minutes: %d' % (stats['total_seconds_read'] // 60),
                    'Cards reviewed: %d' % stats['flashcards_reviewed']], -1, 'S: back')
            else:
                self.screen = 'settings'
                self.index = 0
                self.render()
        elif self.screen == 'library' and self.total:
            entry = self.entries[self.index - self.page_start]
            if entry['dir']:
                self.library(self.category, entry['key'])
            elif self.category == 'books':
                if self.pending_center is not None:
                    self.pending_center = None
                    self.open_book(entry['key'])
                    self.screen = 'chapters'
                    self.index = 0
                    self.lcd.theme(False)
                    self.load_page()
                else:
                    self.pending_book = entry['key']
                    self.pending_center = time.ticks_ms()
            else:
                self.deck_key = entry['key']
                self.screen = 'deck_options'
                self.index = 0
                self.render()
        elif self.screen == 'deck_options':
            if self.index == 0:
                self.open_deck()
            elif self.index == 1:
                self.screen = 'reset'
                self.index = 0
                self.render()
            else:
                self.library('flashcards', self.folder)
        elif self.screen == 'reset':
            if self.index == 1:
                self.open_deck(True)
            else:
                self.screen = 'deck_options'
                self.render()
        elif self.screen == 'chapters' and self.total:
            self.position = self.entries[self.index - self.page_start][0]
            self.screen = 'read'
            self.lcd.theme(self.theme in ('ORP Night', 'Night'))
            self.save()
            self.render()
        elif self.screen == 'settings':
            if self.index == 0:
                speed = self.settings.get('default_wpm', 300) + 50
                self.settings['default_wpm'] = 150 if speed > 500 else speed
            elif self.index == 1:
                self.settings['chapter_auto_pause'] = not self.settings.get('chapter_auto_pause', False)
            else:
                options = (0, 15, 30, 45, 60, 90)
                current = self.settings.get('sleep_timer', 0)
                self.settings['sleep_timer'] = options[(options.index(current) + 1) % len(options)] if current in options else 0
            self.link.rpc('settings', values=self.settings)
            self.render()

    def open_deck(self, reset=False):
        self.card = self.link.rpc('deck', key=self.deck_key, reset=reset)
        self.flipped = False
        self.card_page = 0
        self.screen = 'cards'
        self.render()

    def hold(self, key):
        self.pending_center = None
        if self.screen == 'read':
            if self.running:
                return
            if key == 'center':
                self.save()
                self.home()
            else:
                self.position = max(0, min(self.book['total'] - 1, self.position + (-10 if key == 'left' else 10)))
                self.seeking = True
                self.render()
        elif key == 'center':
            self.save()
            self.home()

    def event(self, event):
        if event.get('disconnect'):
            self.disconnect()
            return
        key = event.get('key')
        if key not in ('left', 'center', 'right'):
            return
        if event['down']:
            if key not in self.held:
                self.held[key] = [time.ticks_ms(), False, time.ticks_ms()]
        elif key in self.held:
            _, did_hold, _ = self.held.pop(key)
            if not did_hold:
                self.tap(key)
            elif self.screen == 'read' and self.seeking and key != 'center':
                self.start()

    def disconnect(self):
        print('__TEMPO_DIAG__ disconnect age=%d' % time.ticks_diff(time.ticks_ms(), self.link.last_seen))
        self.running = False
        self.held = {}
        self.pending_center = None
        self.link.connected = False
        self.screen = 'waiting'
        self.lcd.theme(False)
        self.lcd.menu('Tempo Pico', ['Mac helper disconnected.', 'Reading paused. Reopen the helper.'], -1)

    def tick(self):
        now = time.ticks_ms()
        # Drain a bounded number of serial characters per cycle.
        for _ in range(512):
            if not self.link.poll.poll(0):
                break
            self.link.receive()
        while self.link.events:
            self.event(self.link.events.pop(0))
        if time.ticks_diff(now, self.link.last_seen) > 3500:
            self.disconnect()
            return
        for key, state in list(self.held.items()):
            if not state[1] and time.ticks_diff(now, state[0]) >= HOLD_MS:
                state[1] = True
                state[2] = now
                self.hold(key)
            elif state[1] and key != 'center' and time.ticks_diff(now, state[2]) >= 120:
                state[2] = now
                self.hold(key)
        if self.pending_center is not None and time.ticks_diff(now, self.pending_center) >= DOUBLE_MS:
            self.pending_center = None
            if self.screen == 'read':
                self.start()
            elif self.screen == 'library':
                self.open_book(self.pending_book)
            elif self.screen == 'cards':
                self.flipped = not self.flipped
                self.card_page = 0
                self.render()
        if self.screen == 'read':
            minutes = self.settings.get('sleep_timer', 0)
            if minutes and self.running and time.ticks_diff(now, self.opened_at) >= minutes * 60000:
                self.pause()
                self.opened_at = now
            if self.running and time.ticks_diff(now, self.due) >= 0:
                self.words_read += 1
                self.seconds_read += self.word_delay / 1000
                if self.position >= self.book['total'] - 1:
                    self.pause()
                else:
                    self.position += 1
                    if self.current()[2] and self.settings.get('chapter_auto_pause', False):
                        self.pause()
                    else:
                        self.schedule()
                        self.render()
            if time.ticks_diff(now, self.last_save) > 5000:
                self.save()

    def run(self):
        while True:
            try:
                if not self.link.connected:
                    self.link.rpc('hello')
                    self.link.events = []
                    self.settings = self.link.rpc('settings')
                    self.held = {}
                    self.home()
                self.tick()
            except Exception as error:
                print('__TEMPO_DIAG__ ' + str(error))
                self.running = False
                self.held = {}
                self.pending_center = None
                if not self.link.connected:
                    self.disconnect()
                    time.sleep_ms(250)
                else:
                    self.screen = 'error'
                    self.lcd.theme(False)
                    self.lcd.menu('Could not open content', [str(error)[:50]], -1, 'S: back')
            time.sleep_ms(2)


Tempo().run()
