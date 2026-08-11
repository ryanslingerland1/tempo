import json
from pathlib import Path


DATA_DIR = Path(__file__).parent / "data"
PROGRESS_FILE = DATA_DIR / "progress.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
STATS_FILE = DATA_DIR / "stats.json"

# Zero-width non-joiner: an invisible marker the converter (companion side)
# drops on a chapter heading's first word. Must match CHAPTER_MARKER in
# companion/converter.py.
CHAPTER_MARKER = "‌"


def read_json(filename):
    with open(filename, encoding="utf-8") as file:
        return json.load(file)


def load_book(filename):
    with open(filename, encoding="utf-8") as file:
        text = file.read()
    words = []
    paragraph_ends = set()
    chapters = []
    for paragraph in text.split("\n\n"):
        paragraph_words = paragraph.split()
        if not paragraph_words:
            continue
        if paragraph_words[0].startswith(CHAPTER_MARKER):
            paragraph_words[0] = paragraph_words[0][len(CHAPTER_MARKER):]
            chapters.append((len(words), " ".join(paragraph_words)))
        words.extend(paragraph_words)
        paragraph_ends.add(len(words) - 1)
    if not words:
        raise ValueError(f"{filename} has no book text.")
    return words, Path(filename).stem.replace("_", " ").title(), paragraph_ends, chapters


def book_word_count(filename):
    with open(filename, encoding="utf-8") as file:
        return len(file.read().split())


def load_cards(filename):
    data = read_json(filename)
    cards = data.get("cards", [])
    if not all(isinstance(card, dict) and {"front", "back"} <= card.keys() for card in cards):
        raise ValueError(f"{filename} cards must each contain 'front' and 'back'.")
    return cards, data.get("title", Path(filename).stem.replace("_", " ").title())


def save_progress(book, position, wpm, theme):
    DATA_DIR.mkdir(exist_ok=True)
    data = read_json(PROGRESS_FILE) if PROGRESS_FILE.exists() else {}
    data[book] = {"position": position, "wpm": wpm, "theme": theme}
    with open(PROGRESS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def load_progress(book, default_wpm=300):
    if not PROGRESS_FILE.exists():
        return 0, default_wpm, None
    entry = read_json(PROGRESS_FILE).get(book, {})
    return entry.get("position", 0), entry.get("wpm", default_wpm), entry.get("theme")


def load_settings():
    if not SETTINGS_FILE.exists():
        return {}
    return read_json(SETTINGS_FILE)


def save_settings(settings):
    DATA_DIR.mkdir(exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(settings, file, indent=2)


def load_stats():
    if not STATS_FILE.exists():
        return {"total_words_read": 0, "total_seconds_read": 0}
    return read_json(STATS_FILE)


def save_stats(stats):
    DATA_DIR.mkdir(exist_ok=True)
    with open(STATS_FILE, "w", encoding="utf-8") as file:
        json.dump(stats, file, indent=2)
