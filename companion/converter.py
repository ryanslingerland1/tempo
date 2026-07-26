"""Convert ebooks into the plain-text format the Pico reader expects.

Paragraphs are separated by a blank line (RSVPReader uses that to detect
paragraph breaks for pacing); words within a paragraph are whitespace
separated, matching what bookmanager.load_book parses.
"""
import argparse
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote")


def epub_to_text(path):
    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    paragraphs = []
    for idref, linear in book.spine:
        if linear == "no":
            continue
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        soup = BeautifulSoup(item.get_content(), "xml")
        for tag in soup.find_all(BLOCK_TAGS):
            text = " ".join(tag.get_text(" ", strip=True).split())
            if text:
                paragraphs.append(text)
    if not paragraphs:
        raise ValueError(f"No readable text found in {path}")
    return "\n\n".join(paragraphs)


CONVERTERS = {
    ".epub": epub_to_text,
}


def convert(input_path, output_path):
    input_path = Path(input_path)
    converter = CONVERTERS.get(input_path.suffix.lower())
    if converter is None:
        supported = ", ".join(sorted(CONVERTERS))
        raise NotImplementedError(
            f"No converter yet for '{input_path.suffix}' files (supported: {supported})"
        )
    text = converter(input_path)
    Path(output_path).write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Path to the source ebook")
    parser.add_argument("output", help="Path to write the Pico-formatted .txt file")
    args = parser.parse_args()
    convert(args.input, args.output)


if __name__ == "__main__":
    main()
