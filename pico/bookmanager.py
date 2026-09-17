import json
import time
from pathlib import Path


DATA_DIR = Path(__file__).parent / "data"
PROGRESS_FILE = DATA_DIR / "progress.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
STATS_FILE = DATA_DIR / "stats.json"
FLASHCARD_SESSIONS_FILE = DATA_DIR / "flashcard_sessions.json"

# Zero-width non-joiner: an invisible marker the converter (companion side)
# drops on a chapter heading's first word. Must match CHAPTER_MARKER in
# companion/converter.py.
CHAPTER_MARKER = "‌"

# A small metadata header the converter writes at the top of the file, kept
# as separate Title/Author fields (rather than one string) so a future
# sort-by-author or sort-by-title feature has clean data to work with.
# Must match META_SENTINEL in companion/converter.py.
META_SENTINEL = "%%TEMPO-META%%"


def read_json(filename):
    with open(filename, encoding="utf-8") as file:
        return json.load(file)


def _split_meta_header(text):
    """Strip a leading %%TEMPO-META%% header block, if present, returning
    (title, author, remaining_text). Books converted before this feature
    existed have no header, so title/author both come back None.
    """
    if not text.startswith(META_SENTINEL):
        return None, None, text
    header, _sep, rest = text.partition("\n\n")
    title = None
    author = None
    for line in header.splitlines()[1:]:
        if line.startswith("Title:"):
            title = line[len("Title:"):].strip()
        elif line.startswith("Author:"):
            author = line[len("Author:"):].strip()
    return title, author, rest


def load_book(filename):
    with open(filename, encoding="utf-8") as file:
        text = file.read()
    title, author, text = _split_meta_header(text)
    if title is None:
        title = Path(filename).stem.replace("_", " ").title()
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
    return words, title, author, paragraph_ends, chapters


def book_word_count(filename):
    with open(filename, encoding="utf-8") as file:
        text = file.read()
    _title, _author, text = _split_meta_header(text)
    return len(text.split())


def peek_book_meta(filename):
    """Read just the title/author header, without parsing the whole book
    into words — cheap enough to call once per book when building a sorted
    list. Falls back to a filename-derived title when there's no header."""
    title = None
    author = None
    with open(filename, encoding="utf-8") as file:
        if file.readline().strip() == META_SENTINEL:
            for line in file:
                line = line.strip()
                if not line:
                    break
                if line.startswith("Title:"):
                    title = line[len("Title:"):].strip()
                elif line.startswith("Author:"):
                    author = line[len("Author:"):].strip()
    if not title:
        title = Path(filename).stem.replace("_", " ").title()
    return title, author


def load_cards(filename):
    data = read_json(filename)
    cards = data.get("cards", [])
    if not all(isinstance(card, dict) and {"front", "back"} <= card.keys() for card in cards):
        raise ValueError(f"{filename} cards must each contain 'front' and 'back'.")
    return cards, data.get("title", Path(filename).stem.replace("_", " ").title())


def _flashcard_session_key(filename):
    """Use a project-relative path so decks with the same filename do not collide."""
    path = Path(filename).resolve()
    project_root = Path(__file__).parent.resolve()
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def _valid_cards(cards):
    return isinstance(cards, list) and all(
        isinstance(card, dict) and {"front", "back"} <= card.keys() for card in cards
    )


def load_flashcard_session(filename, default_cards):
    """Return a deck's saved active pile and selected card position.

    A missing session deliberately differs from an empty saved pile: an empty
    pile means the user completed that deck and should see "Deck complete".
    """
    if not FLASHCARD_SESSIONS_FILE.exists():
        return list(default_cards), 0

    sessions = read_json(FLASHCARD_SESSIONS_FILE).get("decks", {})
    session = sessions.get(_flashcard_session_key(filename))
    if not isinstance(session, dict) or not _valid_cards(session.get("cards")):
        return list(default_cards), 0

    cards = session["cards"]
    if not cards:
        return [], 0
    position = session.get("position", 0)
    if not isinstance(position, int):
        position = 0
    return cards, max(0, min(position, len(cards) - 1))


def save_flashcard_session(filename, cards, position):
    """Persist the remaining flashcard pile and the next card to show."""
    DATA_DIR.mkdir(exist_ok=True)
    data = read_json(FLASHCARD_SESSIONS_FILE) if FLASHCARD_SESSIONS_FILE.exists() else {}
    decks = data.setdefault("decks", {})
    decks[_flashcard_session_key(filename)] = {
        "cards": cards,
        "position": 0 if not cards else max(0, min(position, len(cards) - 1)),
    }
    with open(FLASHCARD_SESSIONS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def reset_flashcard_session(filename):
    """Remove a deck's saved pile so its next opening starts fresh."""
    if not FLASHCARD_SESSIONS_FILE.exists():
        return
    data = read_json(FLASHCARD_SESSIONS_FILE)
    decks = data.get("decks", {})
    key = _flashcard_session_key(filename)
    if key not in decks:
        return
    decks.pop(key)
    data["decks"] = decks
    with open(FLASHCARD_SESSIONS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def save_progress(book, position, wpm, theme):
    DATA_DIR.mkdir(exist_ok=True)
    data = read_json(PROGRESS_FILE) if PROGRESS_FILE.exists() else {}
    data[book] = {"position": position, "wpm": wpm, "theme": theme, "last_read": time.time()}
    with open(PROGRESS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def load_progress(book, default_wpm=300):
    if not PROGRESS_FILE.exists():
        return 0, default_wpm, None
    entry = read_json(PROGRESS_FILE).get(book, {})
    return entry.get("position", 0), entry.get("wpm", default_wpm), entry.get("theme")


def load_last_read(book):
    if not PROGRESS_FILE.exists():
        return 0
    entry = read_json(PROGRESS_FILE).get(book, {})
    return entry.get("last_read", 0)


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
