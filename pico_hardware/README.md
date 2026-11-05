# Tempo Pico — separate hardware copy

This folder is independent of the original `pico/` desktop prototype and
`companion/` converter. Its books, desktop source and saved data were copied
when this version was created. Editing or reading here does not update the
original library or progress. Add future converted `.txt` books to this
folder's `books/` directory.

## Start

1. Plug in the Pico normally. Keep Thonny and other serial tools closed.
2. Double-click **Start Tempo Pico.command**, or run:

   ```sh
   python3 mac_helper.py
   ```

3. Keep the helper window focused. Menus and reading appear on the LCD.

The helper needs macOS Python 3 with Tkinter (the same GUI toolkit as the
original desktop app). No pip dependencies are required. With multiple boards,
use `python3 mac_helper.py --port /dev/cu.usbmodem11101` and substitute your port.

## Controls

| Keyboard | Logical button |
| --- | --- |
| Left arrow / A | Left |
| Space / Enter / S | Center |
| Right arrow / D | Right |

- Menus: left/right move, center selects, hold center returns home.
- Book list: center opens a book paused; double-center opens its chapter list.
- Reading: left/right change speed by 25 WPM; center pauses.
- Paused: center starts after the double-tap window; double-center changes theme.
- Paused: hold left/right seeks in ten-word steps, matching the current desktop
  implementation. Releasing resumes. Nearby words appear while seeking.
- Paused: hold center saves and returns home.
- Flashcards: left keeps, right marks known, center flips. Double-center pages
  through long text. Hold center returns home. The deck menu offers a reset
  with a separate confirmation.
- Stats: any tap returns home.

Keyboard capture is limited to the focused helper window. Switching apps
releases held keys. Closing the helper or losing USB pauses the Pico. Reopening
the helper reconnects to the home menu; choose the book to resume saved progress.

## What runs where

The Pico runs menus, key gesture handling, reading timing, chapter pauses,
sleep timer, themes and LCD drawing. The Mac reads books from `books/`, supplies
at most 40 words per request, and writes state to this copy's `data/` directory.
It also serves JSON decks from `flashcards/`. Existing paragraph, punctuation,
long-word and first-name pacing rules are reused from `reader.py`.

Progress saves on pause, returning home, changing paused speed/theme, and every
five seconds during reading. A sudden disconnect can lose the last five seconds.
The Pico needs the Mac helper running; standalone SD-card reading is not included.

The LCD uses a built-in bitmap font, not the desktop's system fonts. It starts
with small black text on white and a red ORP letter. Available hardware themes
are ORP, ORP Night, Classic and Night; Classic/Night show one centered word.
Unsupported Unicode characters are simplified for the LCD font. Extremely long
words are clipped at the smallest size. Settings include default speed, chapter
auto-pause and sleep timer. Desktop font selection and library sorting are not
in this hardware UI. The unchanged desktop app is still available as `main.py`;
its original instructions are in `README_DESKTOP.md`.

## Install or reinstall firmware

The Pico must already have MicroPython installed. Close the helper and Thonny:

```sh
python3 install_device.py
```

The installer saves existing `main.py` and `lcd.py` under `device_backups/` on the
Mac, stages both new files, checks them byte-for-byte, compiles them on the board,
and restarts the Pico. It refuses to use an occupied serial port. It uses the
[MicroPython raw REPL protocol](https://docs.micropython.org/en/latest/reference/repl.html#raw-mode-and-raw-paste-mode).

Alternatively, copy `device/lcd.py` and `device/main.py` to the Pico using Thonny,
then disconnect Thonny and launch the helper. Keep the desktop `main.py` on the
Mac; only `device/main.py` belongs on the board.

To restore the previous board code, copy the files from the relevant
`device_backups/<timestamp>/` directory back to the Pico using Thonny. A `.status`
file records whether each original file existed.

## Display wiring

The working NV3007 initialization is preserved: SPI0, SCK GP18, MOSI GP19,
CS GP17, DC GP20, RST GP21, 428×142 landscape with a 12-row controller offset.
The renderer composes each word into a reusable 32-row buffer and sends the
changed rectangle in one SPI write. A second buffer packs the rotated pixels;
no full-screen framebuffer is needed. The status footer updates at most four
times per second during reading, with immediate updates for mode/speed changes.
The hardware display is rotated 180 degrees. Set `ROTATE_180 = False` in
`device/lcd.py` and reinstall to restore the original orientation.

## Checks

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q .
```

Optional live test, with the helper/Thonny closed:

```sh
python3 tests/usb_smoke.py /dev/cu.usbmodem11101
```

The live test opens a copied book, reads briefly and saves progress in this copy.
It checks USB behavior, not the physical appearance of the LCD.

Display timing benchmark (close the helper first):

```sh
python3 tests/bench_display.py /dev/cu.usbmodem11101
```

The optimized renderer measured about 14.5 ms per word on the connected RP2040
with the benchmark word sequence (previously 128 ms). This measures drawing,
not the LCD panel's physical refresh or USB book-fetch latency. Use `--fast`
with the live smoke test to exercise 1,000 WPM; it saves that speed in the
hardware copy's test book progress.
