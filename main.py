import tkinter as tk
from reader import RSVPReader
from bookmanager import load_book


words = load_book("books/example.txt")

reader = RSVPReader(words)


root = tk.Tk()
root.title("RSVP Reader")
root.geometry("500x300")


word_display = tk.Label(
    root,
    text="",
    font=("Arial", 40)
)

word_display.pack(expand=True)


status = tk.Label(root, text="")
status.pack()


def update():

    if reader.running:

        word_display.config(
            text=reader.current_word()
        )

        status.config(
            text=f"WPM: {reader.wpm}"
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