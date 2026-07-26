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


def _fix_leading_caps(text):
    """Undo the drop-cap/small-caps effect many novels use to open a chapter
    (e.g. a styled "S" followed by "HE RAN" in small caps). As plain text
    this reads as a jarring all-caps run, so bring it down to sentence case.
    """
    match = LEADING_CAPS_RE.match(text)
    if not match:
        return text
    run = match.group(1)
    return run[0] + run[1:].lower() + text[len(run):]


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
        fixed_opening = False
        for tag in soup.find_all(BLOCK_TAGS):
            # No separator: adjacent inline tags (e.g. a styled drop-cap span
            # right before the rest of the word) usually have no real space
            # between them in the source, so inserting one would be wrong.
            text = " ".join(tag.get_text().split())
            if not text:
                continue
            if heading is None and tag.name in HEADING_TAGS:
                heading = text
            # Chapter numbers/subtitles are short lines; the drop-cap effect
            # only ever lands on the chapter's first real (long) paragraph,
            # so only look for it there — never on short title-like lines.
            if not fixed_opening and len(text) > TITLE_LINE_MAX_LENGTH:
                text = _fix_leading_caps(text)
                fixed_opening = True
            paragraphs.append(text)
        if heading is None and paragraphs and len(paragraphs[0]) <= 50:
            heading = paragraphs[0]
        yield heading, paragraphs


def epub_to_text(path, skip_front_matter=True):
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
    return "\n\n".join(paragraphs)


def epub_title(path):
    titles = _read_epub(path).get_metadata("DC", "title")
    return titles[0][0] if titles else None


CONVERTERS = {
    ".epub": epub_to_text,
}

TITLE_READERS = {
    ".epub": epub_title,
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


def convert(input_path, output_path, skip_front_matter=True):
    input_path = Path(input_path)
    converter = CONVERTERS.get(input_path.suffix.lower())
    if converter is None:
        supported = ", ".join(sorted(CONVERTERS))
        raise NotImplementedError(
            f"No converter yet for '{input_path.suffix}' files (supported: {supported})"
        )
    text = converter(input_path, skip_front_matter=skip_front_matter)
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
    parser.set_defaults(skip_front_matter=True)
    args = parser.parse_args()
    convert(args.input, args.output, skip_front_matter=args.skip_front_matter)


if __name__ == "__main__":
    main()
