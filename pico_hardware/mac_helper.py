"""USB book server and focused keyboard controller. macOS, Python 3, no pip dependencies."""
import argparse
import glob
import json
import os
import queue
import select
import termios
import threading
import time
import tkinter as tk
from tkinter import ttk

from bridge import LibraryService


class SerialConnection:
    def __init__(self, port):
        self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        self.original = termios.tcgetattr(self.fd)
        attrs = termios.tcgetattr(self.fd)
        attrs[0] = attrs[1] = attrs[3] = 0
        attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        attrs[4] = attrs[5] = termios.B115200
        attrs[6][termios.VMIN] = 0
        attrs[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)

    def send(self, message):
        self.write((json.dumps(message, ensure_ascii=True) + '\n').encode())

    def write(self, payload):
        data = memoryview(payload)
        deadline = time.monotonic() + 3
        while data:
            if time.monotonic() > deadline:
                raise TimeoutError('USB write timed out')
            if select.select([], [self.fd], [], 0.1)[1]:
                try:
                    data = data[os.write(self.fd, data):]
                except BlockingIOError:
                    pass

    def close(self):
        try:
            termios.tcsetattr(self.fd, termios.TCSANOW, self.original)
        finally:
            os.close(self.fd)


class Helper:
    def __init__(self, root, port):
        self.root = root
        self.port = port
        self.outgoing = queue.Queue()
        self.messages = queue.Queue()
        self.stop = threading.Event()
        self.held = set()
        self.release_jobs = {}
        root.title('Tempo Pico — Mac keyboard & book server')
        root.geometry('580x285')
        self.status = tk.StringVar(value='Connecting to ' + port)
        ttk.Label(root, text='Tempo Pico', font=('Helvetica', 22, 'bold')).pack(pady=18)
        ttk.Label(root, textvariable=self.status, wraplength=550).pack(pady=8)
        ttk.Label(root, text='Keep this window focused for keyboard control.\n\nLeft / A     •     Space / Enter / S     •     Right / D\nTaps, holds and double-taps work on the Pico.\n\nBooks and progress live in the separate pico_hardware copy.', justify='center').pack()
        root.bind('<KeyPress>', self.press)
        root.bind('<KeyRelease>', self.release)
        root.bind('<FocusOut>', self.focus_out)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()
        root.after(50, self.update)

    @staticmethod
    def button(event):
        return {'a': 'left', 'left': 'left', 's': 'center', 'space': 'center', 'return': 'center',
                'd': 'right', 'right': 'right'}.get(event.keysym.lower())

    def press(self, event):
        key = self.button(event)
        if key:
            job = self.release_jobs.pop(key, None)
            if job:
                self.root.after_cancel(job)
            if key not in self.held:
                self.held.add(key)
                self.outgoing.put({'key': key, 'down': True})
            return 'break'

    def release(self, event):
        key = self.button(event)
        if key and key not in self.release_jobs:
            self.release_jobs[key] = self.root.after(20, lambda: self.finish_release(key))
            return 'break'

    def finish_release(self, key):
        self.release_jobs.pop(key, None)
        if key in self.held:
            self.held.remove(key)
            self.outgoing.put({'key': key, 'down': False})

    def focus_out(self, event=None):
        for job in self.release_jobs.values():
            self.root.after_cancel(job)
        self.release_jobs.clear()
        for key in list(self.held):
            self.finish_release(key)

    def run(self):
        connection = None
        try:
            service = LibraryService()
            connection = SerialConnection(self.port)
            if getattr(self, 'reset', False):
                connection.write(b'\r\x03\x03')
                time.sleep(.1)
                connection.write(b'\x04')
            self.messages.put('USB open. Start device/main.py on the Pico, or press its reset button.')
            incoming = bytearray()
            heartbeat = 0
            while not self.stop.is_set() or not self.outgoing.empty():
                while not self.outgoing.empty():
                    connection.send(self.outgoing.get_nowait())
                if time.monotonic() - heartbeat >= 1:
                    connection.send({'ping': True})
                    heartbeat = time.monotonic()
                if not select.select([connection.fd], [], [], 0.02)[0]:
                    continue
                data = os.read(connection.fd, 4096)
                if not data:
                    raise ConnectionError('Pico disconnected')
                incoming.extend(data)
                if len(incoming) > 65536:
                    incoming.clear()
                while b'\n' in incoming:
                    line, _, incoming = incoming.partition(b'\n')
                    try:
                        request = json.loads(line)
                    except (ValueError, UnicodeError):
                        self.messages.put(line.decode(errors='replace'))
                        continue  # Ignore MicroPython startup / diagnostic output.
                    if not isinstance(request, dict) or 'op' not in request or 'id' not in request:
                        continue
                    try:
                        data = service.handle(request['op'], request.get('args', {}))
                        reply = {'id': request['id'], 'ok': True, 'data': data}
                        if request['op'] == 'hello':
                            self.messages.put('Connected — use the keyboard here; watch the LCD.')
                    except Exception as error:
                        reply = {'id': request['id'], 'ok': False, 'error': str(error)}
                    connection.send(reply)
        except Exception as error:
            self.messages.put('Connection stopped: ' + str(error) + '. Close Thonny/other serial tools, then restart this helper.')
        finally:
            if connection:
                connection.close()

    def update(self):
        while not self.messages.empty():
            self.status.set(self.messages.get_nowait())
        self.root.after(50, self.update)

    def close(self):
        self.focus_out()
        self.outgoing.put({'disconnect': True})
        self.stop.set()
        self.worker.join(timeout=4)
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', help='USB serial port, e.g. /dev/cu.usbmodem11101')
    args = parser.parse_args()
    ports = glob.glob('/dev/cu.usbmodem*')
    port = args.port
    if not port:
        if len(ports) != 1:
            parser.error('Specify --port. Found: ' + ', '.join(ports))
        port = ports[0]
    root = tk.Tk()
    Helper(root, port)
    root.mainloop()


if __name__ == '__main__':
    main()
