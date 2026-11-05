"""Mac-side content service. Only this isolated copy's data is written."""
from pathlib import Path
import unicodedata

import bookmanager as bm
from reader import RSVPReader

ROOT = Path(__file__).resolve().parent


def screen_text(text):
    text = text.replace('\u200b', '').replace('\u200c', '')
    for old, new in [('’', "'"), ('‘', "'"), ('“', '"'), ('”', '"'), ('—', '-'), ('–', '-'), ('…', '...')]:
        text = text.replace(old, new)
    return unicodedata.normalize('NFKD', text).encode('ascii', 'replace').decode('ascii')


class LibraryService:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.book = None
        self.cards = None
        self.settings = bm.load_settings()
        self.stats = bm.load_stats()

    def path(self, key, category):
        base = (self.root / category).resolve()
        path = (base / key).resolve()
        if not path.is_relative_to(base):
            raise ValueError('Path is outside the library')
        return path

    def handle(self, op, args):
        if op == 'hello':
            return {'version': 1}
        if op == 'list':
            category = args.get('category', 'books')
            if category not in ('books', 'flashcards'):
                raise ValueError('Unknown library')
            folder = self.path(args.get('folder', ''), category)
            entries = []
            if folder != self.root / category:
                entries.append({'name': '..', 'key': str(folder.parent.relative_to(self.root / category)), 'dir': True})
            for path in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if path.is_dir():
                    entries.append({'name': screen_text(path.name), 'key': str(path.relative_to(self.root / category)), 'dir': True})
                elif path.suffix == ('.txt' if category == 'books' else '.json'):
                    title = bm.peek_book_meta(path)[0] if category == 'books' else bm.read_json(path).get('title', path.stem)
                    entries.append({'name': screen_text(title), 'key': str(path.relative_to(self.root / category)), 'dir': False})
            start = max(0, int(args.get('start', 0)))
            return {'entries': entries[start:start + 5], 'total': len(entries), 'start': start}
        if op == 'open':
            path = self.path(args['key'], 'books')
            words, title, author, ends, chapters = bm.load_book(path)
            key = str(path.relative_to(self.root / 'books'))
            position, wpm, theme = bm.load_progress(key, self.settings.get('default_wpm', 300))
            self.book = {'key': key, 'words': words, 'ends': ends, 'chapters': chapters}
            self.pacing = RSVPReader(words, paragraph_ends=ends)
            return {'title': screen_text(title), 'total': len(words),
                    'position': max(0, min(position, len(words) - 1)),
                    'wpm': max(25, min(1000, wpm)), 'theme': theme or 'ORP'}
        if op == 'chunk':
            if not self.book:
                raise ValueError('Open a book first')
            start = max(0, int(args['start']))
            result = []
            chapter_positions = {p for p, _ in self.book['chapters']}
            for index in range(start, min(start + 40, len(self.book['words']))):
                self.pacing.position = index
                result.append([screen_text(self.book['words'][index])[:96],
                               self.pacing.pause_multiplier(), index in chapter_positions])
            return {'start': start, 'words': result}
        if op == 'save':
            if self.book:
                position = max(0, min(int(args['position']), len(self.book['words']) - 1))
                bm.save_progress(self.book['key'], position, int(args['wpm']), args['theme'])
            return {}
        if op == 'chapters':
            start = max(0, int(args.get('start', 0)))
            chapters = self.book['chapters'] if self.book else []
            return {'entries': [[p, screen_text(t)[:80]] for p, t in chapters[start:start + 5]], 'total': len(chapters)}
        if op == 'settings':
            if 'values' in args:
                self.settings.update(args['values'])
                bm.save_settings(self.settings)
            return self.settings
        if op == 'stats':
            self.stats['total_words_read'] += max(0, int(args.get('words', 0)))
            self.stats['total_seconds_read'] += max(0, float(args.get('seconds', 0)))
            bm.save_stats(self.stats)
            return self.stats
        if op == 'deck':
            path = self.path(args['key'], 'flashcards')
            cards, title = bm.load_cards(path)
            self.deck_path = path
            if args.get('reset'):
                bm.reset_flashcard_session(path)
            self.cards, self.card_index = bm.load_flashcard_session(path, cards)
            self.card_total = len(cards)
            return self.card_data(title)
        if op == 'card':
            if self.cards:
                if args['known']:
                    self.cards.pop(self.card_index)
                else:
                    self.card_index += 1
                self.card_index = self.card_index % len(self.cards) if self.cards else 0
                bm.save_flashcard_session(self.deck_path, self.cards, self.card_index, self.card_total)
                bm.record_flashcard_result()
                self.stats = bm.load_stats()
            return self.card_data()
        raise ValueError('Unknown operation: ' + op)

    def card_data(self, title='Flashcards'):
        card = self.cards[self.card_index] if self.cards else {'front': 'Deck complete', 'back': 'Hold S to return'}
        return {'title': screen_text(title), 'remaining': len(self.cards),
                'front': screen_text(str(card['front']))[:2000], 'back': screen_text(str(card['back']))[:2000]}
