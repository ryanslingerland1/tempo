import json
from pathlib import Path


DATA_DIR = Path(__file__).parent / "data"
PROGRESS_FILE = DATA_DIR / "progress.json"


def read_json(filename):
    with open(filename, encoding="utf-8") as file:
        return json.load(file)


def load_book(filename):
    with open(filename, encoding="utf-8") as file:
        words = file.read().split()
    if not words:
        raise ValueError(f"{filename} has no book text.")
    return words, Path(filename).stem.replace("_", " ").title()


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
