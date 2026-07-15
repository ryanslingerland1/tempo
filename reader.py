class RSVPReader:
    def __init__(self, words, wpm=300, position=0):
        if not words:
            raise ValueError("A book needs at least one word.")
        self.words = words
        self.position = max(0, min(position, len(words) - 1))
        self.wpm = max(25, wpm)
        self.running = False

    def current_word(self):
        return self.words[self.position]

    def move(self, amount):
        self.position = max(0, min(self.position + amount, len(self.words) - 1))

    def delay(self):
        return 60 / self.wpm

    def increase_speed(self):
        self.wpm += 25

    def decrease_speed(self):
        self.wpm = max(25, self.wpm - 25)
