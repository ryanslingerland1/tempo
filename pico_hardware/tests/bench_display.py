"""Opt-in on-board LCD timing benchmark; closes with a Pico soft reset."""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from install_device import RawREPL
from mac_helper import SerialConnection

connection = SerialConnection(sys.argv[1])
try:
    repl = RawREPL(connection)
    repl.enter()
    print(repl.execute('''
import time, gc, lcd
screen = lcd.Display()
gc.collect()
print('free bytes:', gc.mem_free())
samples = []
for i in range(20):
    started = time.ticks_us()
    screen.word(('reading', 'through', 'the', 'window')[i % 4], 'Reading | 1000 WPM | %d/10000' % i)
    samples.append(time.ticks_diff(time.ticks_us(), started))
print('word render us: min=%d avg=%d max=%d' % (min(samples), sum(samples)//len(samples), max(samples)))
print(lcd.spi)
for label in ('pack', 'glyph', 'send', 'line'):
    started = time.ticks_us()
    for i in range(10):
        if label == 'pack':
            lcd.pack_pixels(screen.buf, screen.tx, 0, 428, 32, 1)
        elif label == 'glyph':
            screen.glyph_text('reading', 100, 4, 3, pivot=2)
        elif label == 'send':
            screen.send(55, 32)
        else:
            screen.line('Reading | 1000 WPM | 123/10000', 126)
    print(label, 'avg us:', time.ticks_diff(time.ticks_us(), started)//10)
'''))
    connection.write(b'\x02')
    time.sleep(.1)
    connection.write(b'\x04')
finally:
    connection.close()
