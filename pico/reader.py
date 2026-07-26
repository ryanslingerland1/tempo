import string

SENTENCE_PAUSE = 3.0
CLAUSE_PAUSE = 2.0
PARAGRAPH_PAUSE = 3.75
LONG_WORD_PAUSE = 1.7
LONG_WORD_LENGTH = 9
ELLIPSIS_PAUSE = 4.5


class RSVPReader:
    def __init__(self, words, wpm=300, position=0, paragraph_ends=None):
        if not words:
            raise ValueError("A book needs at least one word.")
        self.words = words
        self.position = max(0, min(position, len(words) - 1))
        self.wpm = max(25, wpm)
        self.running = False
        self.paragraph_ends = paragraph_ends or set()

    def current_word(self):
        return self.words[self.position]

    def move(self, amount):
        self.position = max(0, min(self.position + amount, len(self.words) - 1))

    def delay(self):
        return 60 / self.wpm * self.pause_multiplier()

    def pause_multiplier(self):
        if self.position in self.paragraph_ends:
            return PARAGRAPH_PAUSE
        # Strip closing wrappers (straight AND curly/smart quotes, since
        # converted ebooks use "..."/'...' almost exclusively) so the real
        # sentence-ending punctuation underneath is what gets checked.
        stripped = self.current_word().rstrip("\"'’”)]")
        if stripped:
            if stripped[-1] == "…":
                return ELLIPSIS_PAUSE
            if stripped[-1] in ".!?":
                return SENTENCE_PAUSE
            if stripped[-1] in ",;:":
                return CLAUSE_PAUSE
        bare = self.current_word().strip(string.punctuation + "‘’“”")
        if len(bare) >= LONG_WORD_LENGTH:
            return LONG_WORD_PAUSE
        return 1.0

    def increase_speed(self):
        self.wpm += 25

    def decrease_speed(self):
        self.wpm = max(25, self.wpm - 25)
