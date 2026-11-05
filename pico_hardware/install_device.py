"""Back up, upload and verify the isolated Tempo firmware via MicroPython raw REPL."""
import argparse
import base64
import glob
import json
import os
from pathlib import Path
import select
import subprocess
import time

from mac_helper import SerialConnection

ROOT = Path(__file__).resolve().parent


class RawREPL:
    def __init__(self, connection):
        self.connection = connection
        self.pending = b''

    def until(self, marker, timeout=8):
        deadline = time.monotonic() + timeout
        while marker not in self.pending:
            if time.monotonic() > deadline:
                raise TimeoutError('No response from MicroPython raw REPL')
            if select.select([self.connection.fd], [], [], .05)[0]:
                self.pending += os.read(self.connection.fd, 4096)
        output, _, self.pending = self.pending.partition(marker)
        return output

    def enter(self):
        self.connection.write(b'\r\x03\x03')
        time.sleep(.2)
        self.connection.write(b'\r\x01')
        self.until(b'raw REPL; CTRL-B to exit\r\n>')

    def execute(self, code):
        data = code.encode()
        for start in range(0, len(data), 128):
            self.connection.write(data[start:start + 128])
            time.sleep(.005)
        self.connection.write(b'\x04')
        self.until(b'OK')
        output = self.until(b'\x04')
        error = self.until(b'\x04')
        self.until(b'>')
        if error:
            raise RuntimeError(error.decode(errors='replace'))
        return output.decode().strip()

    def read_file(self, name):
        code = "import os, binascii\nprint(binascii.b2a_base64(open(%r,'rb').read()).decode().strip() if %r in os.listdir() else 'MISSING')" % (name, name)
        result = self.execute(code)
        return None if result == 'MISSING' else base64.b64decode(result)

    def write_file(self, name, data):
        self.execute("f=open(%r,'wb'); f.close()" % name)
        for start in range(0, len(data), 384):
            encoded = base64.b64encode(data[start:start + 384]).decode()
            self.execute("import binascii\nf=open(%r,'ab'); f.write(binascii.a2b_base64(%r)); f.close()" % (name, encoded))
        if self.read_file(name) != data:
            raise RuntimeError('Upload verification failed: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port')
    args = parser.parse_args()
    ports = glob.glob('/dev/cu.usbmodem*')
    if not args.port and len(ports) != 1:
        parser.error('Specify --port. Found: ' + ', '.join(ports))
    port = args.port or ports[0]
    busy = subprocess.run(['lsof', '-t', port], capture_output=True, text=True)
    if busy.stdout.strip():
        parser.error('USB port is busy. Close Thonny and the Mac helper first.')
    backup = ROOT / 'device_backups' / time.strftime('%Y%m%d-%H%M%S')
    backup.mkdir(parents=True)
    connection = SerialConnection(port)
    repl = RawREPL(connection)
    try:
        repl.enter()
        print('Board:', repl.execute('import os; print(os.uname())'))
        for name in ('main.py', 'lcd.py'):
            old = repl.read_file(name)
            if old is not None:
                (backup / name).write_bytes(old)
            (backup / (name + '.status')).write_text('present' if old is not None else 'absent')
        print('Original board files backed up to', backup)
        # Stage and verify both files before changing either active filename.
        for name in ('lcd.py', 'main.py'):
            data = (ROOT / 'device' / name).read_bytes()
            repl.write_file(name + '.tempo_new', data)
            # Compile on the board before committing the staged files.
            repl.execute("compile(open(%r).read(), %r, 'exec')" % (name + '.tempo_new', name))
        for name in ('lcd.py', 'main.py'):
            repl.execute("import os\nos.rename(%r, %r)" % (name + '.tempo_new', name))
        print('Firmware uploaded, compiled on Pico and verified byte-for-byte.')
        connection.write(b'\x02')
        time.sleep(.1)
        connection.write(b'\x04')
        print('Pico restarted. Run mac_helper.py now.')
    finally:
        connection.close()


if __name__ == '__main__':
    main()
