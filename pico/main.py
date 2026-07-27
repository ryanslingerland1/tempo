"""Mac prototype for the three-button Pico RSVP reader.

Keyboard controls mirror the physical buttons: Left/A, Space/Enter/S, and
Right/D. Hold a key or the matching on-screen button for the hold actions.
"""

import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path

from bookmanager import load_book, load_cards, load_progress, load_settings, save_progress, save_settings
from reader import RSVPReader


ROOT = Path(__file__).parent
TOP_LEVEL_MENU_ITEMS = (("Books", ROOT / "books"), ("Flashcards", ROOT / "flashcards"), ("Settings", None))
HOLD_MS = 500
REPEAT_MS = 200
SEEK_INITIAL_REPEAT_MS = 350
SEEK_MIN_REPEAT_MS = 80
SEEK_ACCELERATION_MS = 15

THEMES = (
    {"name": "Classic", "bg": "#f7f4ed", "fg": "#202020", "accent": "#c02a2a"},
    {"name": "Night", "bg": "#1d2025", "fg": "#e8edf2", "accent": "#75c7ff"},
    {"name": "Sepia", "bg": "#eee0c0", "fg": "#4a3520", "accent": "#8b3f22"},
    {"name": "Focus", "bg": "#101010", "fg": "#f5f5f5", "accent": "#f2c94c", "single_word": True},
    {"name": "ORP", "bg": "#f7f7f7", "fg": "#202020", "accent": "#d62f2f", "single_word": True, "orp": True},
    {"name": "ORP Night", "bg": "#000000", "fg": "#ffffff", "accent": "#ff4b4b", "single_word": True, "orp": True},
)

SETTING_SPECS = (
    {
        "key": "chapter_auto_pause",
        "label": "Pause at chapters",
        "options": (True, False),
        "format": lambda value: "On" if value else "Off",
    },
    {
        "key": "default_wpm",
        "label": "Default speed",
        "options": (150, 200, 250, 300, 350, 400, 450, 500),
        "format": lambda value: f"{value} WPM",
    },
    {
        "key": "default_theme",
        "label": "Default theme",
        "options": tuple(theme["name"] for theme in THEMES),
        "format": lambda value: value,
    },
)


class TempoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tempo RSVP Reader")
        self.root.geometry("428x142")
        self.root.minsize(428, 142)

        self.did_hold = {
            "left": False,
            "center": False,
            "right": False,
        }
        self.theme_index = 0
        self.settings = load_settings()
        self.settings_index = 0
        self.screen = "menu"
        self.menu_items = []
        self.menu_index = 0
        self.menu_path = None
        self.reader = None
        self.book_path = None
        self.chapters = []
        self.chapter_titles_by_position = {}
        self.chapter_book_path = None
        self.chapter_items = []
        self.chapter_index = 0
        self.cards = []
        self.card_index = 0
        self.card_flipped = False
        self.held = {"left": False, "center": False, "right": False}
        self.hold_jobs = {}
        self.repeat_jobs = {}
        self.pending_release_jobs = {}
        self.seek_repeat_count = {"left": 0, "right": 0}
        self.read_job = None
        self.pending_center_tap = None
        self.scrolling_preview = False

        self.title_label = tk.Label(root, font=("Helvetica", 16, "bold"))
        self.content = tk.Frame(root)
        self.status = tk.Label(root, font=("Helvetica", 12))
        self.controls = tk.Frame(root)
        self.set_chrome_visible(title=True, status=True)

        controls = self.controls
        self.buttons = {}
        # for name, text in (("left", "LEFT"), ("center", "CENTER"), ("right", "RIGHT")):
        #     button = tk.Button(controls, text=text, width=16, height=2)
        #     button.pack(side="left", padx=8)
        #     button.bind("<ButtonPress-1>", lambda event, key=name: self.press(key))
        #     button.bind("<ButtonRelease-1>", lambda event, key=name: self.release(key))
        #     self.buttons[name] = button

        self.bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.show_menu()

    def set_chrome_visible(self, title, status):
        # pack_forget() followed by a later pack() re-adds a widget at the
        # END of the packing order rather than its old spot, which silently
        # breaks the top-to-bottom layout. Always unpack everything and
        # rebuild the order from scratch so it's never order-dependent.
        for widget in (self.title_label, self.content, self.status, self.controls):
            widget.pack_forget()
        if title:
            self.title_label.pack(pady=(20, 4))
        self.content.pack(expand=True, fill="both", padx=30)
        if status:
            self.status.pack(pady=6)
        self.controls.pack(pady=(0, 20))

    def bind_keys(self):
        bindings = {"left": ("<Left>", "<a>", "<A>"), "center": ("<space>", "<Return>", "<s>", "<S>"), "right": ("<Right>", "<d>", "<D>")}
        for name, keys in bindings.items():
            for key in keys:
                self.root.bind(key, lambda event, name=name: self.key_press(name))
                self.root.bind(key.replace("<", "<KeyRelease-"), lambda event, name=name: self.key_release(name))

    def key_press(self, button):
        # The OS auto-repeats a held key as rapid fake release/press pairs.
        # If a release is still pending when the next press arrives, it's
        # just repeat noise for the same hold, not a real release.
        pending = self.pending_release_jobs.pop(button, None)
        if pending:
            self.root.after_cancel(pending)
            return "break"
        if not self.held[button]:
            self.press(button)
        return "break"

    def key_release(self, button):
        self.pending_release_jobs[button] = self.root.after(20, lambda: self.finish_release(button))
        return "break"

    def finish_release(self, button):
        self.pending_release_jobs.pop(button, None)
        self.release(button)

    def press(self, button):
        if self.held[button]:
            return

        self.held[button] = True
        if button in self.seek_repeat_count:
            self.seek_repeat_count[button] = 0
        self.hold_jobs[button] = self.root.after(HOLD_MS, lambda: self.start_hold(button))

    def release(self, button):
        if not self.held[button]:
            return
        self.held[button] = False
        job = self.hold_jobs.pop(button, None)

        if job:
            self.root.after_cancel(job)

        # Only perform a tap if a hold never happened
        if not self.did_hold[button]:
            self.tap(button)

        self.did_hold[button] = False
        if job := self.repeat_jobs.pop(button, None):
            self.root.after_cancel(job)
        if button in self.seek_repeat_count:
            self.seek_repeat_count[button] = 0
        if button in ("left", "right") and self.scrolling_preview:
            self.scrolling_preview = False
            self.render_reading()

    def start_hold(self, button):
        self.hold_jobs.pop(button, None)

        if self.held[button]:
            self.did_hold[button] = True
            self.hold(button)

    def repeat(self, button):
        if self.held[button]:
            self.hold(button)

    def tap(self, button):
        if self.screen == "menu":
            if button == "left":
                self.move_menu(-1)
            elif button == "right":
                self.move_menu(1)
            elif self.selected_menu_book_path():
                self.menu_center_tap()
            else:
                self.select_menu()
        elif self.screen == "chapters":
            if button == "left":
                self.move_chapters(-1)
            elif button == "right":
                self.move_chapters(1)
            else:
                self.select_chapter()
        elif self.screen == "settings":
            if button == "left":
                self.move_settings(-1)
            elif button == "right":
                self.move_settings(1)
            else:
                self.select_setting()
        elif self.screen == "read":
            if self.reader.running:
                if button == "left":
                    self.reader.decrease_speed()
                elif button == "right":
                    self.reader.increase_speed()
                else:
                    self.pause_reading()
            else:
                if button == "left":
                    self.reader.decrease_speed()
                elif button == "right":
                    self.reader.increase_speed()
                else:
                    self.paused_center_tap()
                self.render_reading()
        elif self.screen == "cards":
            if button == "left":
                self.next_card(known=False)
            elif button == "right":
                self.next_card(known=True)
            else:
                self.card_flipped = not self.card_flipped
                self.render_card()

    def hold(self, button):
        if button == "center" and self.pending_center_tap:
            self.root.after_cancel(self.pending_center_tap)
            self.pending_center_tap = None
        if self.screen == "menu" and button == "center":
            self.root.destroy()
            return
        if self.screen == "chapters" and button == "center":
            self.screen = "menu"
            self.render_menu()
            return
        if self.screen == "settings" and button == "center":
            self.screen = "menu"
            self.render_menu()
            return
        if self.screen == "read":
            if self.reader.running:
                return
            if button == "center" and not self.reader.running:
                self.return_to_menu()
                return
            if button == "left":
                self.reader.move(-10)
            elif button == "right":
                self.reader.move(10)
            if button in ("left", "right") and not self.reader.running:
                self.scrolling_preview = True
            self.render_reading()
        elif self.screen == "cards" and button == "center":
            self.return_to_menu()
            return
        if self.held[button]:
            interval = REPEAT_MS
            if self.screen == "read" and not self.reader.running and button in self.seek_repeat_count:
                interval = max(
                    SEEK_MIN_REPEAT_MS,
                    SEEK_INITIAL_REPEAT_MS - self.seek_repeat_count[button] * SEEK_ACCELERATION_MS,
                )
                self.seek_repeat_count[button] += 1
            self.repeat_jobs[button] = self.root.after(interval, lambda: self.repeat(button))

    def clear_content(self):
        for widget in self.content.winfo_children():
            widget.destroy()

    def show_menu(self):
        self.stop_reading()
        self.screen = "menu"
        self.menu_path = None
        self.menu_items = TOP_LEVEL_MENU_ITEMS
        self.menu_index = 0
        self.render_menu()

    def render_scrolling_list(self, count, selected_index, label_for):
        """Render a vertically-centered, auto-scrolling window of labels —
        shared by the book/flashcard menu and the chapter-jump list, since
        both need the same "show what fits, scroll to keep selection
        visible" behavior on this tiny, fixed-size screen. Returns the
        Label for the selected row so the caller can highlight it — that
        has to happen after apply_theme(), which would otherwise overwrite
        any color set here.
        """
        menu_font = ("Helvetica", 18)
        row_pady = 2
        self.root.update_idletasks()
        available_height = self.content.winfo_height()
        if available_height <= 1:
            available_height = 110
        row_height = tkfont.Font(font=menu_font).metrics("linespace") + 2 * row_pady
        visible_count = max(1, available_height // row_height)

        if count <= visible_count:
            start = 0
        else:
            start = min(max(0, selected_index - visible_count // 2), count - visible_count)

        selected_label = None
        for offset in range(min(visible_count, count - start)):
            index = start + offset
            prefix = "› " if index == selected_index else "  "
            label = tk.Label(self.content, text=prefix + label_for(index), anchor="w", font=menu_font)
            label.pack(fill="x", pady=row_pady)
            if index == selected_index:
                selected_label = label
        return selected_label

    def render_menu(self):
        self.clear_content()
        self.set_chrome_visible(title=False, status=False)
        selected = self.render_scrolling_list(
            len(self.menu_items), self.menu_index, lambda i: self.menu_items[i][0]
        )
        self.apply_theme()
        if selected:
            selected.config(fg="red")

    def move_menu(self, amount):
        self.menu_index = (self.menu_index + amount) % len(self.menu_items)
        self.render_menu()

    def select_menu(self):
        name, path = self.menu_items[self.menu_index]
        if name == "← Back":
            if self.menu_path in (ROOT / "books", ROOT / "flashcards"):
                self.menu_path = None
                self.menu_items = TOP_LEVEL_MENU_ITEMS
            else:
                self.open_menu_folder(path)
            self.menu_index = 0
            self.render_menu()
        elif name == "Settings":
            self.show_settings()
        elif path.is_dir():
            self.open_menu_folder(path)
        elif (ROOT / "books") in path.parents:
            self.start_book(path)
        else:
            self.start_cards(path)

    def selected_menu_book_path(self):
        """The path of the currently highlighted menu row, if (and only if)
        it's an actual book file — not a folder, "Back", or flashcard deck.
        """
        if not self.menu_items:
            return None
        name, path = self.menu_items[self.menu_index]
        if name == "← Back" or path is None or path.is_dir():
            return None
        if (ROOT / "books") in path.parents:
            return path
        return None

    def menu_center_tap(self):
        """A second center tap on a book opens its chapter list instead of
        starting it, mirroring the existing double-tap-for-theme gesture."""
        if self.pending_center_tap:
            self.root.after_cancel(self.pending_center_tap)
            self.pending_center_tap = None
            path = self.selected_menu_book_path()
            if path:
                self.show_chapters(path)
            return
        self.pending_center_tap = self.root.after(300, self.menu_single_tap)

    def menu_single_tap(self):
        self.pending_center_tap = None
        if self.screen == "menu":
            self.select_menu()

    def show_chapters(self, path):
        _words, _title, _paragraph_ends, chapters = load_book(path)
        if not chapters:
            return
        self.chapter_book_path = path
        self.chapter_items = [(None, "← Back")] + chapters
        self.chapter_index = 0
        self.screen = "chapters"
        self.render_chapters()

    def render_chapters(self):
        self.clear_content()
        self.set_chrome_visible(title=False, status=False)
        selected = self.render_scrolling_list(
            len(self.chapter_items), self.chapter_index, lambda i: self.chapter_items[i][1]
        )
        self.apply_theme()
        if selected:
            selected.config(fg="red")

    def move_chapters(self, amount):
        self.chapter_index = (self.chapter_index + amount) % len(self.chapter_items)
        self.render_chapters()

    def select_chapter(self):
        word_index, _title = self.chapter_items[self.chapter_index]
        if word_index is None:
            self.screen = "menu"
            self.render_menu()
            return
        self.start_book(self.chapter_book_path, start_position=word_index)

    def show_settings(self):
        self.settings_index = 0
        self.screen = "settings"
        self.render_settings()

    def settings_row_label(self, index):
        if index == 0:
            return "← Back"
        spec = SETTING_SPECS[index - 1]
        value = self.settings.get(spec["key"], spec["options"][0])
        return f"{spec['label']}: {spec['format'](value)}"

    def render_settings(self):
        self.clear_content()
        self.set_chrome_visible(title=False, status=False)
        selected = self.render_scrolling_list(
            len(SETTING_SPECS) + 1, self.settings_index, self.settings_row_label
        )
        self.apply_theme()
        if selected:
            selected.config(fg="red")

    def move_settings(self, amount):
        self.settings_index = (self.settings_index + amount) % (len(SETTING_SPECS) + 1)
        self.render_settings()

    def select_setting(self):
        if self.settings_index == 0:
            self.screen = "menu"
            self.render_menu()
            return
        spec = SETTING_SPECS[self.settings_index - 1]
        options = spec["options"]
        current = self.settings.get(spec["key"], options[0])
        current_option_index = options.index(current) if current in options else 0
        self.settings[spec["key"]] = options[(current_option_index + 1) % len(options)]
        save_settings(self.settings)
        self.render_settings()

    def open_menu_folder(self, path):
        self.menu_path = path
        entries = [("← Back", path.parent)]
        entries.extend((f"📁 {entry.name}", entry) for entry in sorted(path.iterdir()) if entry.is_dir())
        pattern = "*.txt" if path.is_relative_to(ROOT / "books") else "*.json"
        entries.extend((entry.stem.replace("_", " ").title(), entry) for entry in sorted(path.glob(pattern)))
        self.menu_items = entries
        self.menu_index = 0
        self.render_menu()

    def start_book(self, path, start_position=None):
        words, title, paragraph_ends, chapters = load_book(path)
        default_wpm = self.settings.get("default_wpm", 300)
        position, wpm, saved_theme = load_progress(path.name, default_wpm=default_wpm)
        if start_position is not None:
            position = start_position
        theme_name = saved_theme or self.settings.get("default_theme", THEMES[0]["name"])
        self.theme_index = next(
            (index for index, theme in enumerate(THEMES) if theme["name"] == theme_name), 0
        )
        self.reader = RSVPReader(words, wpm=wpm, position=position, paragraph_ends=paragraph_ends)
        self.chapters = chapters
        self.chapter_titles_by_position = dict(chapters)
        self.book_path = path
        self.screen = "read"
        self.set_chrome_visible(title=False, status=True)
        self.render_reading()
        self.status.config(
            text=f"Paused  •  {self.reader.wpm} WPM ({self.remaining_time_text()})"
            f"  •  {self.reader.position + 1}/{len(self.reader.words)}  •  Center: start"
        )

    def render_reading(self):
        self.clear_content()
        center = self.reader.position
        row = tk.Frame(self.content)
        row.pack(expand=True, fill="both")
        theme = THEMES[self.theme_index]
        self.root.update_idletasks()
        row_width = row.winfo_width()
        if row_width <= 1:
            row_width = self.content.winfo_width()
        if row_width <= 1:
            row_width = 700
        margin = 24
        gap = 20
        focus_font = ("Courier", 26, "bold")
        context_font = ("Courier", 16, "normal")
        focus_word = self.reader.words[center]
        focus_width = tkfont.Font(font=focus_font).measure(focus_word)

        if self.scrolling_preview:
            preview_font = ("Courier", 22, "normal")
            measure = tkfont.Font(font=preview_font)
            available_width = row_width - 48
            preview = [focus_word]
            preview_start = center
            for radius in range(4, 0, -1):
                start = max(0, center - radius)
                end = min(len(self.reader.words), center + radius + 1)
                candidate = self.reader.words[start:end]
                if measure.measure(" ".join(candidate)) <= available_width:
                    preview = candidate
                    preview_start = start
                    break
            x = (row_width - measure.measure(" ".join(preview))) / 2
            highlight_label = None
            space_width = measure.measure(" ")
            for index, word in enumerate(preview):
                label = tk.Label(row, text=word, font=preview_font)
                label.place(x=x, rely=0.5, anchor="w")
                if preview_start + index == center:
                    highlight_label = label
                x += measure.measure(word) + space_width
            self.status.config(text=f"Seeking  •  {self.reader.position + 1}/{len(self.reader.words)}")
            self.apply_theme()
            highlight_label.config(fg=theme["accent"])
            return

        # RSVP works best with one focal word. Add immediate context only when
        # it can sit beside the focal word without crowding or clipping.
        display = [(0, focus_word, focus_font, row_width / 2)]
        if not theme.get("single_word") and 0 < center < len(self.reader.words) - 1:
            left_word = self.reader.words[center - 1]
            right_word = self.reader.words[center + 1]
            context_measure = tkfont.Font(font=context_font)
            left_width = context_measure.measure(left_word)
            right_width = context_measure.measure(right_word)
            left_x = row_width / 2 - focus_width / 2 - gap - left_width / 2
            right_x = row_width / 2 + focus_width / 2 + gap + right_width / 2
            if left_x - left_width / 2 >= margin and right_x + right_width / 2 <= row_width - margin:
                display = [
                    (-1, left_word, context_font, left_x),
                    (0, focus_word, focus_font, row_width / 2),
                    (1, right_word, context_font, right_x),
                ]
        focus_label = None
        for offset, word, font, x in display:
            if offset == 0 and theme.get("orp"):
                marker_index = self.orp_index(word)
                before, marker, after = word[:marker_index], word[marker_index], word[marker_index + 1:]
                font_measure = tkfont.Font(font=font)
                marker_width = font_measure.measure(marker)
                tk.Label(row, text=before, font=font).place(
                    x=x - marker_width / 2, rely=0.5, anchor="e"
                )
                label = tk.Label(row, text=marker, font=font)
                label.place(x=x, rely=0.5, anchor="center")
                tk.Label(row, text=after, font=font).place(
                    x=x + marker_width / 2, rely=0.5, anchor="w"
                )
            else:
                label = tk.Label(row, text=word, font=font)
                label.place(x=x, rely=0.5, anchor="center")
            if offset == 0:
                label.config(fg=theme["accent"])
                focus_label = label
        state = "Reading" if self.reader.running else "Paused"
        self.status.config(
            text=f"{state}  •  {self.reader.wpm} WPM ({self.remaining_time_text()})  •  {self.reader.position + 1}/{len(self.reader.words)}"
        )
        self.apply_theme()
        focus_label.config(fg=theme["accent"])

    def remaining_time_text(self):
        words_remaining = len(self.reader.words) - self.reader.position
        seconds = (words_remaining * 60 + self.reader.wpm - 1) // self.reader.wpm
        if seconds < 60:
            return "<1 min left"
        minutes, seconds = divmod(seconds, 60)
        if minutes < 60:
            return f"{minutes}m left"
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes:02d}m left"

    @staticmethod
    def orp_index(word):
        """Return the character index used as the word's recognition point."""
        letters = [index for index, character in enumerate(word) if character.isalpha()]
        if not letters:
            return 0
        letter_count = len(letters)
        if letter_count == 1:
            position = 0
        elif letter_count <= 5:
            position = 1
        elif letter_count <= 9:
            position = 2
        elif letter_count <= 13:
            position = 3
        else:
            position = 4
        return letters[min(position, letter_count - 1)]

    def paused_center_tap(self):
        """A second center tap while paused changes the reading theme."""
        if self.pending_center_tap:
            self.root.after_cancel(self.pending_center_tap)
            self.pending_center_tap = None
            self.theme_index = (self.theme_index + 1) % len(THEMES)
            self.render_reading()
            self.status.config(text=f"Paused  •  Theme: {THEMES[self.theme_index]['name']}")
        else:
            self.pending_center_tap = self.root.after(300, self.resume_from_paused)

    def resume_from_paused(self):
        self.pending_center_tap = None
        if self.screen == "read" and not self.reader.running:
            self.resume_reading()

    def resume_reading(self):
        self.reader.running = True
        self.read_tick()

    def pause_reading(self):
        self.reader.running = False
        self.stop_reading()
        self.render_reading()
        self.status.config(
            text=f"Paused  •  {self.reader.wpm} WPM ({self.remaining_time_text()})"
            f"  •  {self.reader.position + 1}/{len(self.reader.words)}"
        )

    def read_tick(self):
        if not self.reader.running:
            return
        self.render_reading()
        self.read_job = self.root.after(int(self.reader.delay() * 1000), self.advance_reading)

    def advance_reading(self):
        self.read_job = None
        if not self.reader.running:
            return
        self.reader.move(1)
        if self.settings.get("chapter_auto_pause", True) and self.reader.position in self.chapter_titles_by_position:
            self.pause_for_chapter()
            return
        self.read_tick()

    def pause_for_chapter(self):
        self.reader.running = False
        title = self.chapter_titles_by_position[self.reader.position]
        self.render_reading()
        self.status.config(
            text=f"Chapter: {title}  •  {self.reader.wpm} WPM ({self.remaining_time_text()})"
        )

    def stop_reading(self):
        if self.read_job:
            self.root.after_cancel(self.read_job)
            self.read_job = None
        if self.reader and self.book_path:
            save_progress(
                self.book_path.name,
                self.reader.position,
                self.reader.wpm,
                THEMES[self.theme_index]["name"],
            )
        if self.reader:
            self.reader.running = False

    def return_to_menu(self):
        self.show_menu()

    def close(self):
        self.stop_reading()
        self.root.destroy()

    def start_cards(self, path):
        self.cards, title = load_cards(path)
        self.card_index = 0
        self.card_flipped = False
        self.screen = "cards"
        self.set_chrome_visible(title=True, status=True)
        self.title_label.config(text=title)
        self.render_card()

    def render_card(self):
        self.clear_content()
        if not self.cards:
            tk.Label(self.content, text="Deck complete!", font=("Helvetica", 28, "bold")).pack(expand=True)
            self.status.config(text="Center hold: return to menu")
            self.apply_theme()
            return
        card = self.cards[self.card_index]
        text = card["back"] if self.card_flipped else card["front"]
        side = "Answer" if self.card_flipped else "Question"
        tk.Label(self.content, text=side, font=("Helvetica", 14)).pack(pady=8)
        tk.Label(self.content, text=text, wraplength=700, justify="center", font=("Helvetica", 28, "bold")).pack(expand=True)
        self.status.config(text=f"Card {self.card_index + 1}/{len(self.cards)}  •  Left: keep  Center: flip  Right: know")
        self.apply_theme()

    def next_card(self, known):
        if not self.cards:
            return
        if known:
            self.cards.pop(self.card_index)
            if self.cards:
                self.card_index %= len(self.cards)
        else:
            self.card_index = (self.card_index + 1) % len(self.cards)
        self.card_flipped = False
        self.render_card()

    def apply_theme(self):
        theme = THEMES[self.theme_index]
        self.root.configure(bg=theme["bg"])
        self.content.configure(bg=theme["bg"])
        for widget in (self.title_label, self.status):
            widget.configure(bg=theme["bg"], fg=theme["fg"])
        for child in self.content.winfo_children():
            self._theme_children(child, theme)
        for button in self.buttons.values():
            button.configure(bg=theme["bg"], fg=theme["fg"], activebackground=theme["accent"])

    def _theme_children(self, widget, theme):
        try:
            widget.configure(bg=theme["bg"])
        except tk.TclError:
            pass
        try:
            widget.configure(fg=theme["fg"])
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._theme_children(child, theme)


if __name__ == "__main__":
    root = tk.Tk()
    TempoApp(root)
    root.mainloop()
