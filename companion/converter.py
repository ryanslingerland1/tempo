"""Convert ebooks into the plain-text format the Pico reader expects.

Paragraphs are separated by a blank line (RSVPReader uses that to detect
paragraph breaks for pacing); words within a paragraph are whitespace
separated, matching what bookmanager.load_book parses.
"""
import argparse
import re
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote")
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

NUMBER_WORDS = {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty",
    "seventy", "eighty", "ninety",
}
ROMAN_NUMERAL_RE = re.compile(
    r"^M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$", re.IGNORECASE
)
CHAPTER_KEYWORD_RE = re.compile(r"^(chapter|part|book)\b", re.IGNORECASE)
PROLOGUE_RE = re.compile(r"^prologue\b", re.IGNORECASE)
LEADING_CAPS_RE = re.compile(r"^([A-Z][A-Z']*(?:\s+[A-Z][A-Z']*)+)\b")
TITLE_LINE_MAX_LENGTH = 60

# Common short words that should drop back to lowercase when de-capitalizing
# a styled run (e.g. "RAN" in "SHE RAN"). Anything NOT in this list is left
# capitalized, since it's more likely a proper noun (e.g. "BLY" in
# "HAROLD BLY") than a word this list simply doesn't cover.
COMMON_LOWERCASE_WORDS = {
    "a", "an", "the", "and", "but", "or", "nor", "for", "so", "yet",
    "in", "on", "at", "to", "from", "of", "by", "with", "as", "into",
    "onto", "out", "up", "down", "over", "under", "off", "about",
    "she", "he", "it", "they", "we", "i", "you", "her", "him", "them",
    "his", "its", "their", "our", "your", "my",
    "is", "was", "are", "were", "be", "been", "being",
    "has", "had", "have", "do", "did", "does",
    "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    "not", "no", "if", "then", "than", "that", "this", "these", "those",
    "there", "here", "who", "what", "when", "where", "why", "how",
    "ran", "walked", "said", "went", "came", "saw", "cried", "screamed",
    "turned", "looked", "stood", "sat", "felt", "knew", "thought",
}
ELLIPSIS_RE = re.compile(r"\s*\.(?:\s*\.)+")

# Zero-width space: an invisible pacing hint dropped right after a proper
# name's first appearance in the book. reader.py (pico side) looks for this
# character to give first mentions of a name a beat longer than repeat
# mentions, without ever having to re-scan the book itself. Must match the
# NAME_INTRO_MARKER constant in pico/reader.py.
NAME_INTRO_MARKER = "​"
NAME_RUN_RE = re.compile(r"\b[A-Z][a-z'\-]*(?:\s+[A-Z][a-z'\-]*)+\b")

# Zero-width non-joiner: an invisible marker on the first word of a detected
# chapter heading (e.g. "Chapter One"), so the Pico can build a "jump to
# chapter" list straight from the plain text file without re-detecting
# chapters itself. Must match CHAPTER_MARKER in pico/bookmanager.py.
CHAPTER_MARKER = "‌"

# A small metadata header written at the very top of the output file, kept
# separate from title/author instead of both in one string, so a future
# sort-by-author or sort-by-title feature has clean fields to work with.
# Must match META_SENTINEL/the "Title:"/"Author:" format in
# pico/bookmanager.py.
META_SENTINEL = "%%TEMPO-META%%"


def _normalize_ellipsis(text):
    """Collapse a spaced-out ellipsis ("word . . .") into a single glyph
    attached to the word before it ("word…"), matching how every other bit
    of trailing punctuation attaches with no space. Left as three separate
    lone-period "words", each one flashes on its own in the RSVP reader —
    and each still reads as a full sentence end, tripling the pause.
    """
    return ELLIPSIS_RE.sub("…", text)


def _fix_leading_caps(text):
    """Undo the drop-cap/small-caps effect many novels use to open a scene
    (e.g. a styled "S" followed by "HE RAN", or a whole name like
    "HAROLD BLY"). Each word in the run is judged on its own: common short
    words drop to lowercase ("RAN" -> "ran"), but anything not in that list
    is treated as a likely proper noun and keeps its capital ("BLY").
    """
    match = LEADING_CAPS_RE.match(text)
    if not match:
        return text
    run = match.group(1)
    words = run.split()
    fixed_words = [words[0][0] + words[0][1:].lower()]
    for word in words[1:]:
        if word.lower() in COMMON_LOWERCASE_WORDS:
            fixed_words.append(word.lower())
        else:
            fixed_words.append(word[0] + word[1:].lower())
    return " ".join(fixed_words) + text[len(run):]


def _is_bare_chapter_marker(text):
    """A heading that is *just* a number/word/numeral, e.g. "1", "One", "IV" —
    common in books that label chapters with nothing but a bare marker."""
    core = text.strip(" :.-–—")
    words = core.split()
    if not core or len(words) > 2:
        return False
    if core.isdigit():
        return True
    if core.lower() in NUMBER_WORDS:
        return True
    if core and ROMAN_NUMERAL_RE.match(core):
        return True
    return False


def _mark_name_introductions(paragraphs):
    """Tag the first appearance of each multi-word capitalized name (e.g.
    "Harold Bly") with an invisible marker, so the reader can give a new
    name a beat longer than it gives every later, already-familiar mention.
    """
    seen = set()

    def tag_first_mention(match):
        name = match.group().lower()
        if name in seen:
            return match.group()
        seen.add(name)
        return match.group() + NAME_INTRO_MARKER

    return [NAME_RUN_RE.sub(tag_first_mention, paragraph) for paragraph in paragraphs]


def _looks_like_chapter_start(heading):
    if not heading:
        return False
    text = heading.strip()
    if CHAPTER_KEYWORD_RE.match(text) or PROLOGUE_RE.match(text):
        return True
    return _is_bare_chapter_marker(text)


def _read_epub(path):
    return epub.read_epub(str(path), options={"ignore_ncx": True})


def _epub_sections(book):
    """Yield (heading, paragraphs) per spine document, in reading order.

    `heading` is the document's first heading tag, or its first paragraph
    if short enough to plausibly be a chapter title with no real markup.
    """
    for idref, linear in book.spine:
        if linear == "no":
            continue
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        if isinstance(item, epub.EpubNav):
            continue
        soup = BeautifulSoup(item.get_content(), "xml")
        paragraphs = []
        heading = None
        heading_index = None
        for tag in soup.find_all(BLOCK_TAGS):
            # No separator: adjacent inline tags (e.g. a styled drop-cap span
            # right before the rest of the word) usually have no real space
            # between them in the source, so inserting one would be wrong.
            text = _normalize_ellipsis(" ".join(tag.get_text().split()))
            if not text:
                continue
            if heading is None and tag.name in HEADING_TAGS:
                heading = text
                heading_index = len(paragraphs)
            # Chapter numbers/subtitles are short lines; the drop-cap/small-caps
            # effect is applied at the start of every scene (not just the very
            # first paragraph of a chapter file), but always on a real, long
            # prose paragraph — so use length, not position, to find them.
            if len(text) > TITLE_LINE_MAX_LENGTH:
                text = _fix_leading_caps(text)
            paragraphs.append(text)
        if heading is None and paragraphs and len(paragraphs[0]) <= 50:
            heading = paragraphs[0]
            heading_index = 0
        if heading_index is not None and _looks_like_chapter_start(heading):
            paragraphs[heading_index] = CHAPTER_MARKER + paragraphs[heading_index]
        yield heading, paragraphs


def epub_to_text(path, skip_front_matter=True, mark_name_introductions=True):
    book = _read_epub(path)
    sections = list(_epub_sections(book))

    start = 0
    if skip_front_matter:
        for index, (heading, _paragraphs) in enumerate(sections):
            if _looks_like_chapter_start(heading):
                start = index
                break
        else:
            start = 0  # Nothing matched confidently — keep the whole book.

    paragraphs = [paragraph for _heading, paras in sections[start:] for paragraph in paras]
    if not paragraphs:
        raise ValueError(f"No readable text found in {path}")
    if mark_name_introductions:
        paragraphs = _mark_name_introductions(paragraphs)
    return "\n\n".join(paragraphs)


def epub_title(path):
    titles = _read_epub(path).get_metadata("DC", "title")
    return titles[0][0] if titles else None


def epub_author(path):
    creators = _read_epub(path).get_metadata("DC", "creator")
    return creators[0][0] if creators else None


CONVERTERS = {
    ".epub": epub_to_text,
}

TITLE_READERS = {
    ".epub": epub_title,
}

AUTHOR_READERS = {
    ".epub": epub_author,
}


def suggest_title(path):
    path = Path(path)
    reader = TITLE_READERS.get(path.suffix.lower())
    if reader:
        try:
            title = reader(path)
            if title:
                return title
        except Exception:
            pass
    return path.stem.replace("_", " ").replace("-", " ").title()


def suggest_author(path):
    path = Path(path)
    reader = AUTHOR_READERS.get(path.suffix.lower())
    if reader:
        try:
            author = reader(path)
            if author:
                return author
        except Exception:
            pass
    return ""


def _build_meta_header(title, author):
    lines = [META_SENTINEL]
    if title:
        lines.append(f"Title: {title}")
    if author:
        lines.append(f"Author: {author}")
    return "\n".join(lines)


def strip_meta_header(text):
    """Remove a leading %%TEMPO-META%% header block, if present."""
    if not text.startswith(META_SENTINEL):
        return text
    _header, _sep, rest = text.partition("\n\n")
    return rest


def peek_meta(path):
    """Read just the title/author header (if present) without parsing the
    whole book — used to label entries in the companion's library view.
    Mirrors peek_book_meta in pico/bookmanager.py.
    """
    title = None
    author = None
    with open(path, encoding="utf-8") as file:
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
        title = Path(path).stem.replace("_", " ").title()
    return title, author


def convert(
    input_path,
    output_path,
    skip_front_matter=True,
    mark_name_introductions=True,
    title=None,
    author=None,
):
    input_path = Path(input_path)
    converter = CONVERTERS.get(input_path.suffix.lower())
    if converter is None:
        supported = ", ".join(sorted(CONVERTERS))
        raise NotImplementedError(
            f"No converter yet for '{input_path.suffix}' files (supported: {supported})"
        )
    text = converter(
        input_path,
        skip_front_matter=skip_front_matter,
        mark_name_introductions=mark_name_introductions,
    )
    if title or author:
        text = f"{_build_meta_header(title, author)}\n\n{text}"
    Path(output_path).write_text(text, encoding="utf-8")
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Path to the source ebook")
    parser.add_argument("output", help="Path to write the Pico-formatted .txt file")
    parser.add_argument(
        "--keep-front-matter",
        dest="skip_front_matter",
        action="store_false",
        help="Keep the title page, copyright, TOC, foreword, etc. instead of "
        "jumping straight to the first chapter (default: skip them)",
    )
    parser.add_argument(
        "--no-name-pacing",
        dest="mark_name_introductions",
        action="store_false",
        help="Don't give a name's first appearance a longer pause (default: do)",
    )
    parser.add_argument("--title", help="Book title to embed (defaults to ebook metadata/filename)")
    parser.add_argument("--author", help="Author to embed, so a future sort feature can use it")
    parser.set_defaults(skip_front_matter=True, mark_name_introductions=True)
    args = parser.parse_args()
    convert(
        args.input,
        args.output,
        skip_front_matter=args.skip_front_matter,
        mark_name_introductions=args.mark_name_introductions,
        title=args.title or suggest_title(args.input),
        author=args.author or suggest_author(args.input),
    )


if __name__ == "__main__":
    main()
