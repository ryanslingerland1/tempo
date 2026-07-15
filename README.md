# Tempo

Tempo is a Mac prototype for a three-button RSVP (Rapid Serial Visual Presentation) reader that will later run on a Raspberry Pi Pico.

## Run

The on-screen buttons can be used with the mouse. Keyboard equivalents are:

### Menu

| Button | Action |
| --- | --- |
| Left tap | Move down the menu |
| Center tap | Open the selected folder, book, or flashcard deck |
| Center hold | Quit the app |
| Right tap | Move up the menu |

### Reader — running

| Button | Action |
| --- | --- |
| Left tap | Lower WPM |
| Center tap | Pause |
| Right tap | Raise WPM |
| Left/Right hold | No action |

### Reader — paused

| Button | Action |
| --- | --- |
| Left tap | Lower WPM |
| Center tap | Start reading |
| Center double-tap | Change reading theme |
| Center hold | Return to the menu |
| Right tap | Raise WPM |
| Left/Right hold | Seek one word at a time; release to resume from the highlighted word |

While seeking, Tempo temporarily displays a line of nearby words so it is easy to choose the resume position.

### Flashcards

| Button | Action |
| --- | --- |
| Left tap | Keep the current card in the pile |
| Center tap | Flip the card |
| Center hold | Return to the menu |
| Right tap | Mark the card as known and remove it from the current session |

## Content and saved data

- Put books in `books/` as UTF-8 `.txt` files.
- Put flashcard decks in `flashcards/` as JSON files.
- Tempo saves each book's position, WPM, and selected theme to `data/progress.json`.

### Flashcard deck format

```json
{
  "title": "Example Deck",
  "cards": [
    {
      "front": "What does RSVP mean?",
      "back": "Rapid Serial Visual Presentation."
    }
  ]
}
```

## Reading themes

The default themes can display the focused word with nearby context when it fits. The **Focus** theme always shows one word. The **ORP** and **ORP Night** themes show one word and color its estimated Optimal Recognition Point character.
