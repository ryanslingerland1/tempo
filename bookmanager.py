import json
import os


def load_book(filename):
    with open(filename, "r", encoding="utf-8") as file:
        text = file.read()

    words = text.split()

    return words


def save_progress(book, position, wpm):

    data = {}

    if os.path.exists("data/progress.json"):
        with open("data/progress.json") as f:
            data = json.load(f)

    data[book] = {
        "position": position,
        "wpm": wpm
    }

    with open("data/progress.json", "w") as f:
        json.dump(data, f, indent=4)


def load_progress(book):

    if not os.path.exists("data/progress.json"):
        return 0, 300

    with open("data/progress.json") as f:
        data = json.load(f)

    if book in data:
        return (
            data[book]["position"],
            data[book]["wpm"]
        )

    return 0, 300