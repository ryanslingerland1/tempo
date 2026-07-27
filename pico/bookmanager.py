import json
from pathlib import Path


DATA_DIR = Path(__file__).parent / "data"
PROGRESS_FILE = DATA_DIR / "progress.json"

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


def load_progress(book):
    if not PROGRESS_FILE.exists():
        return 0, 300, None
    entry = read_json(PROGRESS_FILE).get(book, {})
    return entry.get("position", 0), entry.get("wpm", 300), entry.get("theme")
