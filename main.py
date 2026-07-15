import tkinter as tk
from reader import RSVPReader
from bookmanager import load_book


words = load_book("books/example.txt")

reader = RSVPReader(words)


root = tk.Tk()
root.title("RSVP Reader")
root.geometry("900x300")


# Five word display
word_labels = []

word_frame = tk.Frame(root)
word_frame.pack(expand=True, fill="both")

for i in range(5):
    label = tk.Label(
        word_frame,
        text="",
        font=("Courier", 30),
        anchor="center",
        padx=8,
    )
    label.grid(row=0, column=i, sticky="ew")
    word_labels.append(label)

for i in range(5):
    word_frame.grid_columnconfigure(i, weight=1, uniform="word")


status = tk.Label(root, text="")
status.pack()


def update_display():

    center = reader.position

    for i, label in enumerate(word_labels):

        index = center - 2 + i

        if 0 <= index < len(reader.words):
            label.config(
                text=reader.words[index]
            )
        else:
            label.config(
                text=""
            )

        # Highlight center word
        if i == 2:
            label.config(
                fg="red"
            )
        else:
            label.config(
                fg="black"
            )


def update():

    if reader.running:

        update_display()

        status.config(
            text=f"WPM: {reader.wpm} | Word: {reader.position}/{len(reader.words)}"
        )

        reader.next_word()

        root.after(
            int(reader.delay()*1000),
            update
        )


def toggle():

    reader.running = not reader.running

    if reader.running:
        update()


def faster():

    reader.increase_speed()


def slower():

    reader.decrease_speed()



root.bind("<space>", lambda e: toggle())
root.bind("<Right>", lambda e: faster())
root.bind("<Left>", lambda e: slower())


button_frame = tk.Frame(root)
button_frame.pack()


tk.Button(
    button_frame,
    text="- WPM",
    command=slower
).pack(side="left")


tk.Button(
    button_frame,
    text="Pause",
    command=toggle
).pack(side="left")


tk.Button(
    button_frame,
    text="+ WPM",
    command=faster
).pack(side="left")


root.mainloop()