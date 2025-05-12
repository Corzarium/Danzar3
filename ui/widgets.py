import tkinter as tk

def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return "…\n" + text[-max_chars:]

def add_bubble(container, text: str, is_user: bool):
    bg   = "#005f99" if is_user else "#4b0082"
    side = "e" if is_user else "w"
    lbl  = tk.Label(
        container,
        text=text,
        bg=bg, fg="white",
        wraplength=400,
        justify="left",
        font=("Consolas", 12),    # <-- bumped from 11→12
        padx=8, pady=4
    )
    lbl.pack(anchor=side, pady=5)
    container.update_idletasks()
    container.master.yview_moveto(1.0)
