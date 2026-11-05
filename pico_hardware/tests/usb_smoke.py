"""Opt-in live board test. Close other USB tools before running this script."""
import queue
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mac_helper
from bridge import LibraryService


logs = queue.Queue()
class RecordingService(LibraryService):
    def handle(self, op, args):
        print('Board request:', op, flush=True)
        result = super().handle(op, args)
        if '--fast' in sys.argv and op == 'open':
            result['wpm'] = 1000
        if '--fast' in sys.argv and op == 'settings':
            result = dict(result, chapter_auto_pause=False)
        logs.put((op, args, result))
        return result


def wait_for(op, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            event = logs.get(timeout=.1)
        except queue.Empty:
            continue
        if event[0] == op:
            return event
    raise TimeoutError('Board did not request ' + op)


def tap(helper, key):
    helper.outgoing.put({'key': key, 'down': True})
    time.sleep(.09)
    helper.outgoing.put({'key': key, 'down': False})
    time.sleep(.15)


def main():
    mac_helper.LibraryService = RecordingService
    helper = mac_helper.Helper.__new__(mac_helper.Helper)
    helper.port = sys.argv[1]
    helper.reset = '--reset' in sys.argv
    helper.outgoing = queue.Queue()
    helper.messages = queue.Queue()
    helper.stop = threading.Event()
    worker = threading.Thread(target=helper.run, daemon=True)
    worker.start()
    try:
        wait_for('hello')
        wait_for('settings')
        time.sleep(.2)
        tap(helper, 'center')
        listing = wait_for('list')[2]
        # Select first folder/book, skip parent entries; navigate pages as needed.
        for depth in range(8):
            entries = listing['entries']
            target = next((i for i, entry in enumerate(entries) if not entry['dir']), None)
            if target is None:
                target = next(i for i, entry in enumerate(entries) if entry['name'] != '..')
            for _ in range(target):
                tap(helper, 'right')
            tap(helper, 'center')
            if not entries[target]['dir']:
                break
            listing = wait_for('list')[2]
        wait_for('open')
        wait_for('chunk')
        time.sleep(.3)
        tap(helper, 'center')
        time.sleep(1.5)
        tap(helper, 'center')
        wait_for('save')
        stats = wait_for('stats')
        assert stats[1].get('words', 0) > 0, stats
        helper.outgoing.put({'key': 'center', 'down': True})
        time.sleep(.8)
        helper.outgoing.put({'key': 'center', 'down': False})
        wait_for('save')
        print('LIVE PASS: Pico handshake, menus, folder browsing, book opening, chunk delivery, reading, pause, progress save, statistics, hold-to-home.')
    finally:
        helper.outgoing.put({'disconnect': True})
        time.sleep(.2)
        helper.stop.set()
        worker.join(3)
        while not helper.messages.empty():
            print(helper.messages.get())


if __name__ == '__main__':
    main()
