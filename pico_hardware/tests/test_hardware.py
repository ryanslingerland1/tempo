import ast
import importlib.util
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bookmanager as bm
from bridge import LibraryService
import mac_helper


class ContentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'books' / 'nested').mkdir(parents=True)
        (self.root / 'flashcards').mkdir()
        (self.root / 'data').mkdir()
        self.patches = []
        for field, name in [('PROGRESS_FILE', 'progress.json'), ('SETTINGS_FILE', 'settings.json'),
                            ('STATS_FILE', 'stats.json'), ('FLASHCARD_SESSIONS_FILE', 'flashcard_sessions.json')]:
            self.patches.append(patch.object(bm, field, self.root / 'data' / name))
        self.patches.append(patch.object(bm, 'DATA_DIR', self.root / 'data'))
        for item in self.patches:
            item.start()
        content = '%%TEMPO-META%%\nTitle: A test\nAuthor: Writer\n\n\u200cChapter One\n\n' + ' '.join('word%d' % i for i in range(120)) + '.\n\nFinal paragraph.'
        (self.root / 'books' / 'nested' / 'test.txt').write_text(content)
        (self.root / 'flashcards' / 'deck.json').write_text(json.dumps({'cards': [{'front': 'Q', 'back': 'A'}]}))
        self.service = LibraryService(self.root)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_book_chunk_pacing_progress(self):
        listing = self.service.handle('list', {})
        self.assertTrue(listing['entries'][0]['dir'])
        book = self.service.handle('open', {'key': 'nested/test.txt'})
        self.assertEqual(book['title'], 'A test')
        chunk = self.service.handle('chunk', {'start': 0})
        self.assertEqual(len(chunk['words']), 40)
        self.assertTrue(chunk['words'][0][2])
        self.assertNotIn('\u200c', chunk['words'][0][0])
        end = self.service.handle('chunk', {'start': book['total'] - 1})
        self.assertGreater(end['words'][0][1], 1)
        self.service.handle('save', {'position': 81, 'wpm': 350, 'theme': 'ORP Night'})
        resumed = self.service.handle('open', {'key': 'nested/test.txt'})
        self.assertEqual((resumed['position'], resumed['wpm'], resumed['theme']), (81, 350, 'ORP Night'))
        self.assertEqual(self.service.handle('chapters', {})['total'], 1)

    def test_traversal_rejected(self):
        with self.assertRaises(ValueError):
            self.service.handle('open', {'key': '../../outside.txt'})
        with self.assertRaises(ValueError):
            self.service.handle('list', {'category': '../data'})

    def test_deck_completion_persists_and_resets(self):
        self.assertEqual(self.service.handle('deck', {'key': 'deck.json'})['remaining'], 1)
        self.assertEqual(self.service.handle('card', {'known': False})['remaining'], 1)
        self.assertEqual(self.service.handle('card', {'known': True})['remaining'], 0)
        self.assertEqual(self.service.handle('deck', {'key': 'deck.json'})['remaining'], 0)
        self.assertEqual(self.service.handle('deck', {'key': 'deck.json', 'reset': True})['remaining'], 1)
        self.assertEqual(self.service.handle('stats', {})['flashcards_reviewed'], 2)

    def test_pagination(self):
        for i in range(13):
            (self.root / 'books' / ('%02d.txt' % i)).write_text('words')
        result = self.service.handle('list', {'start': 5})
        self.assertEqual(result['total'], 14)
        self.assertEqual(len(result['entries']), 5)
        self.assertEqual(self.service.handle('list', {'start': 10})['entries'][0]['key'], '09.txt')

    def test_usb_transport_fragmented_requests(self):
        master, slave = os.openpty()
        port = os.ttyname(slave)
        helper = mac_helper.Helper.__new__(mac_helper.Helper)
        helper.port = port
        helper.outgoing = queue.Queue()
        helper.messages = queue.Queue()
        helper.stop = threading.Event()
        with patch.object(mac_helper, 'LibraryService', return_value=self.service):
            worker = threading.Thread(target=helper.run)
            worker.start()
            time.sleep(0.05)
            request = json.dumps({'id': 7, 'op': 'open', 'args': {'key': 'nested/test.txt'}}).encode() + b'\n'
            os.write(master, request[:13])
            os.write(master, request[13:])
            received = b''
            deadline = time.monotonic() + 3
            found = None
            import select
            while time.monotonic() < deadline and found is None:
                if select.select([master], [], [], .1)[0]:
                    received += os.read(master, 8192)
                    while b'\n' in received:
                        line, _, received = received.partition(b'\n')
                        message = json.loads(line)
                        if message.get('id') == 7:
                            found = message
            helper.stop.set()
            worker.join(2)
        os.close(master)
        os.close(slave)
        self.assertIsNotNone(found)
        self.assertTrue(found['ok'])
        self.assertEqual(found['data']['title'], 'A test')


class FakeLCD:
    def __init__(self):
        self.calls = []
    def __getattr__(self, key):
        return lambda *args, **kw: self.calls.append((key, args))


class FirmwareTests(ContentTests):
    def setUp(self):
        super().setUp()
        self.clock = 1000
        self.fake_time = types.SimpleNamespace(ticks_ms=lambda: self.clock,
            ticks_diff=lambda a, b: a - b, ticks_add=lambda a, b: a + b,
            sleep_ms=lambda ms: None)
        source = ast.parse((ROOT / 'device' / 'main.py').read_text())
        source.body.pop()  # Do not start the infinite hardware loop.
        namespace = {}
        with patch.dict(sys.modules, {'lcd': types.SimpleNamespace(Display=FakeLCD), 'time': self.fake_time}):
            exec(compile(source, 'device/main.py', 'exec'), namespace)
        self.app = namespace['Tempo']()
        service = self.service
        self.app.link = types.SimpleNamespace(connected=True, events=[], last_seen=self.clock,
            rpc=lambda op, **args: service.handle(op, args),
            poll=types.SimpleNamespace(poll=lambda ms: []))
        self.app.settings = {}
        self.app.open_book('nested/test.txt')

    def test_first_connection_home(self):
        self.app.home()
        self.assertEqual(self.app.screen, 'home')
        self.app.tap('center')
        self.assertEqual(self.app.screen, 'library')

    def test_tap_double_tap_hold_and_release(self):
        self.app.tap('right')
        self.assertEqual(self.app.wpm, 325)
        self.app.tap('center')
        self.clock += 100
        self.app.tap('center')
        self.assertFalse(self.app.running)
        self.assertEqual(self.app.theme, 'ORP Night')
        self.app.tap('center')
        self.clock += 301
        self.app.tick()
        self.assertTrue(self.app.running)
        self.app.tap('center')
        self.assertFalse(self.app.running)
        self.app.event({'key': 'right', 'down': True})
        self.clock += 501
        self.app.tick()
        self.assertEqual(self.app.position, 10)
        self.app.event({'key': 'right', 'down': False})
        self.assertTrue(self.app.running)

    def test_heartbeat_disconnect_pauses(self):
        self.app.start()
        self.clock += 4000
        self.app.tick()
        self.assertFalse(self.app.running)
        self.assertFalse(self.app.link.connected)
        self.assertEqual(self.app.screen, 'waiting')

    def test_last_word_stops_and_saves(self):
        self.app.position = self.app.book['total'] - 1
        self.app.start()
        self.clock = self.app.due + 1
        self.app.link.last_seen = self.clock
        self.app.tick()
        self.assertFalse(self.app.running)
        self.assertEqual(bm.load_progress('nested/test.txt')[0], self.app.position)

    def test_chapter_selection(self):
        self.app.library('books', 'nested')
        self.app.index = 1  # Parent folder is row zero.
        self.app.tap('center')
        self.app.tap('center')
        self.assertEqual(self.app.screen, 'chapters')
        self.app.tap('center')
        self.assertEqual(self.app.screen, 'read')
        self.assertEqual(self.app.position, 0)


if __name__ == '__main__':
    unittest.main()
