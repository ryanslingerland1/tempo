import string

MIN_WPM = 25
MAX_WPM = 1000

SENTENCE_PAUSE = 3.0
CLAUSE_PAUSE = 2.0
PARAGRAPH_PAUSE = 3.75
LONG_WORD_PAUSE = 1.7
LONG_WORD_LENGTH = 9
ELLIPSIS_PAUSE = 4.5
NAME_INTRO_PAUSE = 2.2

# Zero-width space: an invisible pacing hint the converter (companion side)
# drops right after a name's first appearance in the book. Must match the
# NAME_INTRO_MARKER constant in companion/converter.py.
NAME_INTRO_MARKER = "​"


class RSVPReader:
    def __init__(self, words, wpm=300, position=0, paragraph_ends=None):
        if not words:
            raise ValueError("A book needs at least one word.")
        self.words = words
        self.position = max(0, min(position, len(words) - 1))
        self.wpm = max(MIN_WPM, min(MAX_WPM, wpm))
        self.running = False
        self.paragraph_ends = paragraph_ends or set()

    def current_word(self):
        return self.words[self.position]

    def move(self, amount):
        self.position = max(0, min(self.position + amount, len(self.words) - 1))

    def delay(self):
        return 60 / self.wpm * self.pause_multiplier()

    def pause_multiplier(self):
        word = self.current_word()

        if self.position in self.paragraph_ends:
            base = PARAGRAPH_PAUSE
        else:
            # Strip closing wrappers (straight AND curly/smart quotes, since
            # converted ebooks use "..."/'...' almost exclusively, plus the
            # invisible name marker) so the real punctuation underneath is
            # what gets checked.
            stripped = word.rstrip("\"'’”)]" + NAME_INTRO_MARKER)
            if stripped and stripped[-1] == "…":
                base = ELLIPSIS_PAUSE
            elif stripped and stripped[-1] in ".!?":
                base = SENTENCE_PAUSE
            elif stripped and stripped[-1] in ",;:":
                base = CLAUSE_PAUSE
            else:
                bare = word.strip(string.punctuation + "‘’“”" + NAME_INTRO_MARKER)
                base = LONG_WORD_PAUSE if len(bare) >= LONG_WORD_LENGTH else 1.0

        if NAME_INTRO_MARKER in word:
            return max(base, NAME_INTRO_PAUSE)
        return base

    def increase_speed(self):
        self.wpm = min(MAX_WPM, self.wpm + 25)

    def decrease_speed(self):
        self.wpm = max(MIN_WPM, self.wpm - 25)
