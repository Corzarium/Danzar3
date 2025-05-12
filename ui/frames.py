# ui/frames.py

import os
import json
import tkinter as tk
from tkinter import ttk
from ui.widgets import add_bubble

# Theme colors
DARK_BG       = "#2e2e2e"
PANEL_BG      = "#1e1e1e"
ACCENT_PURPLE = "#6a0dad"
TEXT_FG       = "#ffffff"

def build_config_frame(parent, cfg):
    """
    Left panel: profile selector & settings.
    Returns (canvas, frame, monitor_var, profile_var, loaded_profile_dict)
    """
    frame = tk.Frame(parent, bg=PANEL_BG)
    frame.pack(side="left", fill="y")
    canvas = tk.Canvas(frame, bg=PANEL_BG, highlightthickness=0)
    canvas.pack(fill="both", expand=True, padx=5, pady=5)

    # --- Monitor selector ---
    tk.Label(canvas, text="Monitor:", bg=PANEL_BG, fg=TEXT_FG).pack(anchor="w")
    monitor_var = tk.IntVar(value=cfg.get("monitor_index", 1))
    monitors = list(range(1, 5))  # adjust if more monitors
    mon_menu = ttk.Combobox(
        canvas, textvariable=monitor_var, values=monitors, state="readonly",
        width=5
    )
    mon_menu.pack(anchor="w", pady=(0,10))

    # --- Profile loader ---
    tk.Label(canvas, text="Profile:", bg=PANEL_BG, fg=TEXT_FG).pack(anchor="w")
    profiles = [f[:-5] for f in os.listdir("profiles") if f.endswith(".json")]
    profile_var = tk.StringVar(value=cfg.get("selected_profile", profiles[0] if profiles else ""))
    prof_menu = ttk.Combobox(
        canvas, textvariable=profile_var, values=profiles, state="readonly"
    )
    prof_menu.pack(anchor="w", pady=(0,5))

    # Load the selected profile JSON for later use
    profile_path = os.path.join("profiles", profile_var.get() + ".json")
    loaded_profile = {}
    try:
        with open(profile_path, "r") as f:
            loaded_profile = json.load(f)
    except FileNotFoundError:
        pass

    return canvas, frame, monitor_var, profile_var, loaded_profile


def build_preview_frame(parent, controller):
    """
    Right panel: screenshot preview + ROI overlays.
    Returns (canvas, frame)
    """
    frame = tk.Frame(parent, bg=PANEL_BG)
    frame.pack(side="right", fill="y")
    canvas = tk.Canvas(frame, bg=DARK_BG, width=300, height=300, highlightthickness=1, relief="sunken")
    canvas.pack(padx=8, pady=8)
    return canvas, frame


def build_chat_frame(parent, controller):
    """
    Center: chat history + entry + toolbar.
    Returns: chat_canvas, bubble_frame, entry, send_btn, screenshot_btn, mic_btn, auto_btn, batch_btn
    """
    # --- chat display ---
    outer = tk.Frame(parent, bg=DARK_BG)
    outer.pack(fill="both", expand=True)

    chat_canvas = tk.Canvas(outer, bg=DARK_BG, highlightthickness=0)
    scrollbar = tk.Scrollbar(outer, orient="vertical", command=chat_canvas.yview)
    chat_canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    chat_canvas.pack(side="left", fill="both", expand=True)

    bubble_frame = tk.Frame(chat_canvas, bg=DARK_BG)
    chat_canvas.create_window((0, 0), window=bubble_frame, anchor="nw")
    bubble_frame.bind("<Configure>", lambda e: chat_canvas.configure(scrollregion=chat_canvas.bbox("all")))

    # --- bottom toolbar ---
    toolbar = tk.Frame(parent, bg=PANEL_BG)
    toolbar.pack(fill="x", padx=5, pady=5)

    entry = tk.Entry(toolbar, bg=DARK_BG, fg=TEXT_FG, insertbackground=TEXT_FG)
    entry.pack(side="left", fill="x", expand=True, padx=(0,5))

    send_btn = tk.Button(
        toolbar, text="➡️ Send",
        bg=ACCENT_PURPLE, fg=TEXT_FG,
        command=controller._on_send_click
    )
    send_btn.pack(side="left", padx=2)

    screenshot_btn = tk.Button(
        toolbar, text="📸",
        bg=ACCENT_PURPLE, fg=TEXT_FG,
        command=controller._take_screenshot
    )
    screenshot_btn.pack(side="left", padx=2)

    mic_btn = tk.Button(
        toolbar, text="🎤",
        bg=ACCENT_PURPLE, fg=TEXT_FG,
        command=getattr(controller, "_toggle_mic", lambda: None)
    )
    mic_btn.pack(side="left", padx=2)

    auto_btn = tk.Button(
        toolbar, text="💬 Commentary",
        bg=ACCENT_PURPLE, fg=TEXT_FG
    )
    auto_btn.pack(side="left", padx=2)

    batch_btn = tk.Button(
        toolbar, text="📸 Batch Send",
        bg=ACCENT_PURPLE, fg=TEXT_FG
    )
    batch_btn.pack(side="left", padx=2)

    return chat_canvas, bubble_frame, entry, send_btn, screenshot_btn, mic_btn, auto_btn, batch_btn
