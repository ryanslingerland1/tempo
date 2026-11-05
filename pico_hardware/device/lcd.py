"""NV3007 LCD driver, using the pinout/init from the working screen test."""
from machine import Pin, SPI
import time
import framebuf
import micropython

WIDTH = 428
HEIGHT = 142
Y_OFFSET = 12
STRIP_HEIGHT = 32
WHITE = 0xFFFF
BLACK = 0
RED = 0x00F8  # RGB565 red, byte-swapped for direct SPI writes.
ROTATE_180 = True


@micropython.viper
def pack_pixels(source, target, x: int, width: int, height: int, rotate: int):
    """Pack a dirty rectangle for one SPI write, including optional rotation."""
    src = ptr16(source)
    dst = ptr16(target)
    output = 0
    step = 1
    if rotate:
        step = -1
    for row in range(height):
        if rotate:
            source_index = (height - 1 - row) * 428 + x + width - 1
        else:
            source_index = row * 428 + x
        for column in range(width):
            dst[output] = src[source_index]
            output += 1
            source_index += step


@micropython.viper
def scaled_glyph(buf, atlas, code: int, x: int, y: int, scale: int, ink: int):
    """Blit one cached 8x8 glyph directly into the RGB565 strip."""
    pixels = ptr16(buf)
    masks = ptr8(atlas)
    for gy in range(8):
        mask = int(masks[(code - 32) * 8 + gy])
        for gx in range(8):
            if mask & (1 << gx):
                for sy in range(scale):
                    py = y + gy * scale + sy
                    if py >= 0 and py < 32:
                        for sx in range(scale):
                            px = x + gx * scale + sx
                            if px >= 0 and px < 428:
                                pixels[py * 428 + px] = ink


def init():
    global CS, DC, RST, spi

    # -------------------------
    # PINS
    # -------------------------
    CS  = Pin(17, Pin.OUT, value=1)
    DC  = Pin(20, Pin.OUT, value=1)
    RST = Pin(21, Pin.OUT, value=1)

    spi = SPI(
        0,
        baudrate=50_000_000,
        polarity=0,
        phase=0,
        sck=Pin(18),
        mosi=Pin(19)
    )

    # -------------------------
    # HARDWARE RESET
    # -------------------------
    RST.value(1)
    time.sleep_ms(100)

    RST.value(0)
    time.sleep_ms(100)

    RST.value(1)
    time.sleep_ms(150)


    # -------------------------
    # NV3007 2.79" INIT
    # -------------------------

    commands = [
        (0xFF, b'\xA5'),
        (0x9A, b'\x08'),
        (0x9B, b'\x08'),
        (0x9C, b'\xB0'),
        (0x9D, b'\x16'),
        (0x9E, b'\xC4'),

        (0x8F, b'\x55\x04'),
        (0x84, b'\x90'),
        (0x83, b'\x7B'),
        (0x85, b'\x33'),

        (0x60, b'\x00'),
        (0x70, b'\x00'),
        (0x61, b'\x02'),
        (0x71, b'\x02'),
        (0x62, b'\x04'),
        (0x72, b'\x04'),

        (0x6C, b'\x29'),
        (0x7C, b'\x29'),
        (0x6D, b'\x31'),
        (0x7D, b'\x31'),
        (0x6E, b'\x0F'),
        (0x7E, b'\x0F'),

        (0x66, b'\x21'),
        (0x76, b'\x21'),
        (0x68, b'\x3A'),
        (0x78, b'\x3A'),

        (0x63, b'\x07'),
        (0x73, b'\x07'),
        (0x64, b'\x05'),
        (0x74, b'\x05'),
        (0x65, b'\x02'),
        (0x75, b'\x02'),

        (0x67, b'\x23'),
        (0x77, b'\x23'),
        (0x69, b'\x08'),
        (0x79, b'\x08'),
        (0x6A, b'\x13'),
        (0x7A, b'\x13'),
        (0x6B, b'\x13'),
        (0x7B, b'\x13'),

        (0x6F, b'\x00'),
        (0x7F, b'\x00'),

        (0x50, b'\x00'),
        (0x52, b'\xD6'),
        (0x53, b'\x08'),
        (0x54, b'\x08'),
        (0x55, b'\x1E'),
        (0x56, b'\x1C'),

        (0xA0, b'\x2B\x24\x00'),
        (0xA1, b'\x87'),
        (0xA2, b'\x86'),

        (0xA5, b'\x00'),
        (0xA6, b'\x00'),
        (0xA7, b'\x00'),

        (0xA8, b'\x36'),
        (0xA9, b'\x7E'),
        (0xAA, b'\x7E'),

        (0xB9, b'\x85'),
        (0xBA, b'\x84'),
        (0xBB, b'\x83'),
        (0xBC, b'\x82'),
        (0xBD, b'\x81'),
        (0xBE, b'\x80'),

        (0xBF, b'\x01'),
        (0xC0, b'\x02'),
        (0xC1, b'\x00'),
        (0xC2, b'\x00'),
        (0xC3, b'\x00'),

        (0xC4, b'\x33'),
        (0xC5, b'\x7E'),
        (0xC6, b'\x7E'),

        (0xC8, b'\x33\x33'),

        (0xC9, b'\x68'),
        (0xCA, b'\x69'),
        (0xCB, b'\x6A'),
        (0xCC, b'\x6B'),

        (0xCD, b'\x33\x33'),

        (0xCE, b'\x6C'),
        (0xCF, b'\x6D'),
        (0xD0, b'\x6E'),
        (0xD1, b'\x6F'),

        (0xAB, b'\x03\x67'),
        (0xAC, b'\x03\x6B'),
        (0xAD, b'\x03\x68'),
        (0xAE, b'\x03\x6C'),

        (0xB3, b'\x00'),
        (0xB4, b'\x00'),
        (0xB5, b'\x00'),

        (0xB6, b'\x32'),
        (0xB7, b'\x7E'),
        (0xB8, b'\x7E'),

        (0xE0, b'\x00'),
        (0xE1, b'\x03\x0F'),
        (0xE2, b'\x04'),
        (0xE3, b'\x01'),
        (0xE4, b'\x0E'),
        (0xE5, b'\x01'),
        (0xE6, b'\x19'),
        (0xE7, b'\x10'),
        (0xE8, b'\x10'),

        (0xEA, b'\x12'),
        (0xEB, b'\xD0'),
        (0xEC, b'\x04'),
        (0xED, b'\x07'),
        (0xEE, b'\x07'),
        (0xEF, b'\x09'),

        (0xF0, b'\xD0'),
        (0xF1, b'\x0E'),
        (0xF9, b'\x17'),

        (0xF2, b'\x2C\x1B\x0B\x20'),

        (0xE9, b'\x29'),

        (0x35, b'\x00'),
        (0x44, b'\x00\x10'),
        (0x46, b'\x10'),

        (0xFF, b'\x00'),
    ]

    print("Sending initialization...")

    for c, d in commands:
        cmd(c, d)

    # RGB565
    cmd(0x3A, b'\x05')

    # Sleep out
    cmd(0x11)
    time.sleep_ms(200)

    # Display ON
    cmd(0x29)
    time.sleep_ms(100)

    # Inversion ON


    print("Initialization complete")
    # Rotate display 90 degrees into landscape
    cmd(0x36, b'\x60')



# Send a display command and optional data.
def cmd(c, data=b''):
    CS.value(0)
    DC.value(0)
    spi.write(bytes([c]))
    if data:
        DC.value(1)
        spi.write(data)
    CS.value(1)


class Display:
    def __init__(self):
        init()
        self.buf = bytearray(WIDTH * STRIP_HEIGHT * 2)
        self.tx = bytearray(len(self.buf))
        self.fb = framebuf.FrameBuffer(self.buf, WIDTH, STRIP_HEIGHT, framebuf.RGB565)
        self.glyph_buf = bytearray(8)
        self.glyph = framebuf.FrameBuffer(self.glyph_buf, 8, 8, framebuf.MONO_HLSB)
        self.atlas = bytearray(95 * 8)
        for code in range(32, 127):
            self.glyph.fill(0)
            self.glyph.text(chr(code), 0, 0, 1)
            for gy in range(8):
                mask = 0
                for gx in range(8):
                    if self.glyph.pixel(gx, gy):
                        mask |= 1 << gx
                self.atlas[(code - 32) * 8 + gy] = mask
        self.bg = WHITE
        self.fg = BLACK
        self.accent = RED
        self.word_bounds = None
        self.last_context = None
        self.last_status = None
        self.last_status_at = time.ticks_ms()

    def send(self, y, height, x=0, width=WIDTH):
        byte_count = width * height * 2
        pack_pixels(self.buf, self.tx, x, width, height, int(ROTATE_180))
        if ROTATE_180:
            y = HEIGHT - y - height
            x = WIDTH - x - width
        x1 = x + width - 1
        y0 = y + Y_OFFSET
        y1 = y0 + height - 1
        cmd(0x2A, bytes([x >> 8, x & 255, x1 >> 8, x1 & 255]))
        cmd(0x2B, bytes([y0 >> 8, y0 & 255, y1 >> 8, y1 & 255]))
        CS.value(0)
        DC.value(0)
        spi.write(b'\x2C')
        DC.value(1)
        spi.write(memoryview(self.tx)[:byte_count])
        CS.value(1)

    def theme(self, night=False):
        self.bg, self.fg = (BLACK, WHITE) if night else (WHITE, BLACK)
        self.clear()

    def clear(self):
        self.word_bounds = None
        self.last_context = None
        self.last_status = None
        self.fb.fill(self.bg)
        for y in range(0, HEIGHT, STRIP_HEIGHT):
            self.send(y, min(STRIP_HEIGHT, HEIGHT - y))

    def glyph_text(self, text, x, y, scale=1, color=None, pivot=-1):
        color = self.fg if color is None else color
        if scale == 1 and pivot == -1:
            self.fb.text(text, x, y, color)
            return
        for index, char in enumerate(text):
            code = ord(char)
            if code < 32 or code > 126:
                code = 63
            ink = self.accent if index == pivot else color
            scaled_glyph(self.buf, self.atlas, code, x + index * 8 * scale,
                         y, scale, ink)

    def line(self, text, y, selected=False):
        self.fb.fill(self.bg)
        if selected:
            self.fb.fill_rect(0, 0, WIDTH, 16, self.fg)
        self.glyph_text(text[:52], 6, 4, color=self.bg if selected else self.fg)
        self.send(y, 16)

    def menu(self, title, rows, selected, footer='A/S/D: navigate / select'):
        self.clear()
        self.line(title, 0)
        first = max(0, selected - 2)
        first = min(first, max(0, len(rows) - 5))
        for offset, row in enumerate(rows[first:first + 5]):
            self.line(row, 24 + offset * 18, first + offset == selected)
        self.line(footer, HEIGHT - 16)

    def word(self, word, status, orp=True, context=''):
        letters = [i for i, char in enumerate(word) if char.isalpha()]
        n = len(letters)
        p = 0 if n <= 1 else 1 if n <= 5 else 2 if n <= 9 else 3 if n <= 13 else 4
        pivot = letters[p] if letters else 0
        scale = 3
        while scale > 1:
            cell = 8 * scale
            x = WIDTH // 2 - pivot * cell - cell // 2 if orp else (WIDTH - len(word) * cell) // 2
            if x >= 8 and x + len(word) * cell <= WIDTH - 8:
                break
            scale -= 1
        cell = 8 * scale
        x = WIDTH // 2 - pivot * cell - cell // 2 if orp else (WIDTH - len(word) * cell) // 2
        # Compose the entire word off-screen, then send it in ONE transfer.
        self.fb.fill(self.bg)
        self.glyph_text(word, x, (STRIP_HEIGHT - cell) // 2,
                        scale, pivot=pivot if orp else -1)
        left = max(0, min(WIDTH - 1, x))
        right = max(left + 1, min(WIDTH, x + len(word) * cell))
        bounds = (left, right)
        if self.word_bounds is not None:
            left = min(left, self.word_bounds[0])
            right = max(right, self.word_bounds[1])
        self.send((HEIGHT - STRIP_HEIGHT) // 2, STRIP_HEIGHT,
                  x=left, width=right - left)
        self.word_bounds = bounds
        if context != self.last_context:
            self.line(context, 18)
            self.last_context = context
        now = time.ticks_ms()
        # Word progress need not redraw the footer at RSVP speed. Pauses,
        # mode changes and speed changes still update it immediately.
        previous_mode = self.last_status.rsplit('|', 1)[0] if self.last_status else None
        mode = status.rsplit('|', 1)[0]
        if (status != self.last_status and
                (mode != previous_mode or time.ticks_diff(now, self.last_status_at) >= 250)):
            self.line(status, HEIGHT - 16)
            self.last_status = status
            self.last_status_at = now
