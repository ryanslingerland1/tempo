"""Pixel correctness and regression checks without requiring MicroPython."""
import ast
from pathlib import Path
import types
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'device' / 'lcd.py'


def load_display():
    tree = ast.parse(SOURCE.read_text())
    body = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Assign)):
            if isinstance(node, ast.FunctionDef):
                node.decorator_list = []
            body.append(node)
    clock = types.SimpleNamespace(ticks_ms=lambda: 1000, ticks_diff=lambda a, b: a-b)
    scope = {'ptr8': memoryview, 'ptr16': lambda b: memoryview(b).cast('H'), 'time': clock}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(SOURCE), 'exec'), scope)
    return scope


class DisplayTests(unittest.TestCase):
    def test_dirty_rectangle_packing_and_rotation(self):
        scope = load_display()
        source = bytearray(428 * 32 * 2)
        pixels = memoryview(source).cast('H')
        for i in range(len(pixels)):
            pixels[i] = i
        output = bytearray(3 * 2 * 2)
        scope['pack_pixels'](source, output, 10, 3, 2, 0)
        self.assertEqual(list(memoryview(output).cast('H')), [10, 11, 12, 438, 439, 440])
        scope['pack_pixels'](source, output, 10, 3, 2, 1)
        self.assertEqual(list(memoryview(output).cast('H')), [440, 439, 438, 12, 11, 10])
        self.assertEqual(pixels[10], 10)  # Source remains unchanged.

    def test_scaled_pixels_and_clipping(self):
        scope = load_display()
        atlas = bytearray(95 * 8)
        atlas[0] = 0b10000001
        atlas[1] = 0b00011000
        for scale in (1, 2, 3):
            for x, y in ((10, 4), (-3, -2), (424, 29)):
                buf = bytearray(428 * 32 * 2)
                scope['scaled_glyph'](buf, atlas, 32, x, y, scale, 0x00F8)
                pixels = memoryview(buf).cast('H')
                expected = set()
                for gx, gy in ((0, 0), (7, 0), (3, 1), (4, 1)):
                    for sy in range(scale):
                        for sx in range(scale):
                            px, py = x + gx * scale + sx, y + gy * scale + sy
                            if 0 <= px < 428 and 0 <= py < 32:
                                expected.add(py * 428 + px)
                self.assertEqual({i for i, ink in enumerate(pixels) if ink}, expected)
                self.assertTrue(all(pixels[i] == 0x00F8 for i in expected))

    def test_word_is_one_transfer_and_footer_is_throttled(self):
        scope = load_display()
        display = scope['Display'].__new__(scope['Display'])
        display.bg = 0xFFFF
        display.fb = types.SimpleNamespace(fill=lambda color: None)
        display.glyph_text = lambda *args, **kw: None
        sends, lines = [], []
        display.send = lambda y, height, **kw: sends.append((y, height))
        display.line = lambda text, y: lines.append((text, y))
        display.word_bounds = None
        display.last_context = None
        display.last_status = None
        display.last_status_at = 0
        display.word('reading', 'Reading | 1000 WPM | 1/100')
        self.assertEqual(sends, [(55, 32)])
        sends.clear()
        lines.clear()
        display.word('next', 'Reading | 1000 WPM | 2/100')
        self.assertEqual(sends, [(55, 32)])
        self.assertEqual(lines, [])
        display.word('next', 'Paused | 1000 WPM | 2/100')
        self.assertEqual(lines[-1][0], 'Paused | 1000 WPM | 2/100')


if __name__ == '__main__':
    unittest.main()
