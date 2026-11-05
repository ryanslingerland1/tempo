from machine import Pin, SPI
import time

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

def cmd(c, data=b''):
    CS.value(0)
    DC.value(0)
    spi.write(bytes([c]))

    if data:
        DC.value(1)
        spi.write(bytes(data))

    CS.value(1)


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

# -------------------------
# STANDALONE LCD APPEARANCE TEST
# -------------------------
import framebuf

WIDTH = 428
HEIGHT = 142
Y_OFFSET = 12  # Keep the panel offset from your working test.
FONT_SCALE = 3  # Built-in 8px font: 24px tall (previously 48px).
WORD_HEIGHT = 64
Y_START = (HEIGHT - WORD_HEIGHT) // 2
FOCUS_X = WIDTH // 2

BLACK = 0x0000
WHITE = 0xFFFF
# framebuf stores RGB565 little-endian; this panel takes high byte first.
# Black/white are unchanged, but red must be byte-swapped for direct SPI.
ORP_COLOR = 0x00F8

text = """
The morning light came through the window as I opened
the book and started reading without realizing how
quickly the time was passing around me and wondering
where the afternoon had gone
"""
words = text.split()
WPM = 350
WORD_TIME_MS = int(60000 / WPM)

# Reuse a small strip instead of allocating a full-screen framebuffer.
buf = bytearray(WIDTH * WORD_HEIGHT * 2)
word_fb = framebuf.FrameBuffer(buf, WIDTH, WORD_HEIGHT, framebuf.RGB565)


def send_area(y, height):
    y0 = y + Y_OFFSET
    y1 = y0 + height - 1
    x1 = WIDTH - 1
    cmd(0x2A, bytes([0, 0, x1 >> 8, x1 & 0xFF]))
    cmd(0x2B, bytes([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF]))
    CS.value(0)
    DC.value(0)
    spi.write(b'\x2C')
    DC.value(1)
    spi.write(memoryview(buf)[:WIDTH * height * 2])
    CS.value(1)


def clear_screen():
    # Clear ALL visible rows, including those outside the changing word area.
    word_fb.fill(WHITE)
    for y in range(0, HEIGHT, WORD_HEIGHT):
        send_area(y, min(WORD_HEIGHT, HEIGHT - y))


def orp_index(word):
    # Visual pivot heuristic, ignoring punctuation at either end.
    letters = [i for i, char in enumerate(word) if char.isalpha()]
    if not letters:
        return max(0, (len(word) - 1) // 2)
    length = len(letters)
    if length <= 1:
        pivot = 0
    elif length <= 5:
        pivot = 1
    elif length <= 9:
        pivot = 2
    elif length <= 13:
        pivot = 3
    else:
        pivot = 4
    return letters[pivot]


def draw_word(word):
    word_fb.fill(WHITE)
    if not word:
        send_area(Y_START, WORD_HEIGHT)
        return

    pivot = orp_index(word)
    scale = FONT_SCALE
    # Fit both sides of the pivot while keeping its center fixed.
    while scale > 1:
        cell = 8 * scale
        start_x = FOCUS_X - pivot * cell - cell // 2
        if start_x >= 10 and start_x + len(word) * cell <= WIDTH - 10:
            break
        scale -= 1

    cell = 8 * scale
    start_x = FOCUS_X - pivot * cell - cell // 2
    start_y = (WORD_HEIGHT - cell) // 2

    # Render one glyph at a time: avoids large allocations for long words.
    glyph_buf = bytearray(8)
    glyph = framebuf.FrameBuffer(glyph_buf, 8, 8, framebuf.MONO_HLSB)
    for index, char in enumerate(word):
        glyph.fill(0)
        glyph.text(char, 0, 0, 1)
        color = ORP_COLOR if index == pivot else BLACK
        for y in range(8):
            for x in range(8):
                if glyph.pixel(x, y):
                    word_fb.fill_rect(
                        start_x + index * cell + x * scale,
                        start_y + y * scale,
                        scale, scale, color,
                    )

    send_area(Y_START, WORD_HEIGHT)


clear_screen()
while True:
    for word in words:
        start = time.ticks_ms()
        draw_word(word)
        elapsed = time.ticks_diff(time.ticks_ms(), start)
        remaining = WORD_TIME_MS - elapsed
        if remaining > 0:
            time.sleep_ms(remaining)
    time.sleep(1)
