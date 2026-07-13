import time


class RSVPReader:
    def __init__(self, words, wpm=300):
        self.words = words
        self.position = 0
        self.wpm = wpm
        self.running = False

    def current_word(self):
        if self.position < len(self.words):
            return self.words[self.position]
        return None

    def next_word(self):
        if self.position < len(self.words)-1:
            self.position += 1

    def previous_word(self):
        if self.position > 0:
            self.position -= 1

    def delay(self):
        return 60 / self.wpm

    def increase_speed(self):
        self.wpm += 25

    def decrease_speed(self):
        self.wpm = max(25, self.wpm - 25)