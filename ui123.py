# ui.py

import os
import threading
import tempfile
import queue
import time
import tkinter as tk
from tkinter import ttk

import mss
import numpy as np
import cv2
import keyboard
import simpleaudio as sa
import speech_recognition as sr
import pytesseract

from lm_client import LMClient
from rag_client import RAGClient
from tts_client import TTSClient
from config import load_settings, save_settings, list_profiles, load_profile, save_profile

def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return "…\n" + text[-max_chars:]


class DanzarAIApp(tk.Tk):
    def __init__(self, cfg, lm_client: LMClient, rag_client: RAGClient, tts_client: TTSClient):
        super().__init__()
        self.cfg = cfg
        self.lm  = lm_client
        self.rag = rag_client
        self.tts = tts_client

        self._tts_queue   = queue.Queue()
        self.recognizer   = sr.Recognizer()
        self.auto_mode    = False
        self._pause_auto  = False
        self.last_season  = None

        self.commentary_interval = cfg["commentary_interval"]
        self.commentary_batch    = cfg["commentary_batch"]

        self.profile_var  = tk.StringVar(value=cfg["selected_profile"])
        self.interval_var = tk.StringVar(value=str(self.commentary_interval))
        self.batch_var    = tk.StringVar(value=str(self.commentary_batch))

        self.title("Danzar AI")
        self.configure(bg="#2b2b2b")
        self.geometry("800x1000")
        self._build_ui()

        threading.Thread(target=self._setup_hotkeys, daemon=True).start()
        threading.Thread(target=self._tts_player_loop, daemon=True).start()

    def _setup_hotkeys(self):
        keyboard.on_press_key('`',   lambda e: self._start_record())
        keyboard.on_release_key('`', lambda e: self._stop_record())
        keyboard.add_hotkey('ctrl+f10', lambda: self.send_screenshot())
        keyboard.add_hotkey('f7',       lambda: self.toggle_auto())

    def _start_record(self):
        self._pause_auto = True
        self.status.set("Listening…")

    def _stop_record(self):
        try:
            with sr.Microphone() as mic:
                audio = self.recognizer.listen(mic, timeout=5)
            text = self.recognizer.recognize_google(audio)
        except Exception as e:
            text = f"[STT Error: {e}]"
        self.add_bubble(text, True)
        threading.Thread(target=self._handle_user_speech, args=(text,), daemon=True).start()

    def _handle_user_speech(self, text):
        self.status.set("Thinking…")
        reply = self.lm.chat(
            self.text_widgets["System Prompt:"].get("1.0","end").strip(),
            text, temperature=0.7, max_tokens=-1
        )
        self.add_bubble(reply, False)
        self.speak_enqueue(reply)
        self.status.set("Ready")
        self._pause_auto = False

    def _build_ui(self):
        cfgf = tk.Frame(self, bg="#2b2b2b")
        cfgf.pack(fill="x", padx=10, pady=5)
        cfgf.columnconfigure(1, weight=1)
        cfgf.columnconfigure(3, weight=1)
        cfgf.columnconfigure(5, weight=1)

        # Profile dropdown
        tk.Label(cfgf, text="Game Profile:", bg="#2b2b2b", fg="white")\
          .grid(row=0, column=0, sticky="w")
        prof_combo = ttk.Combobox(cfgf, textvariable=self.profile_var,
                                  values=list_profiles(), state="readonly")
        prof_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        prof_combo.bind("<<ComboboxSelected>>", lambda e: self._load_profile())

        # Monitor selector
        tk.Label(cfgf, text="Monitor:", bg="#2b2b2b", fg="white")\
          .grid(row=0, column=2, sticky="w", padx=(20,0))
        mon_names = []
        with mss.mss() as sct:
            for i, m in enumerate(sct.monitors):
                mon_names.append(f"{i}: {m['width']}×{m['height']} @{m['left']},{m['top']}")
        cur_idx = str(self.cfg.get("monitor_index",1)) + ":"
        self.mon_var = tk.StringVar(
            value=next((n for n in mon_names if n.startswith(cur_idx)), mon_names[1])
        )
        mon_combo = ttk.Combobox(cfgf, textvariable=self.mon_var,
                                 values=mon_names, state="readonly")
        mon_combo.grid(row=0, column=3, sticky="ew", padx=5, pady=2)
        mon_combo.bind("<<ComboboxSelected>>", lambda e: self._on_mon_change())

        # Show ROIs toggle
        self.show_rois_var = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(cfgf, text="Show ROIs", variable=self.show_rois_var,
                             bg="#2b2b2b", fg="white", command=self._on_toggle_rois)
        chk.grid(row=0, column=4, padx=20)

        # Interval & batch
        tk.Label(cfgf, text="Interval (s):", bg="#2b2b2b", fg="white")\
          .grid(row=1, column=0, sticky="w")
        tk.Entry(cfgf, textvariable=self.interval_var,
                 bg="#3e3e3e", fg="white")\
          .grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        tk.Label(cfgf, text="Batch Size:", bg="#2b2b2b", fg="white")\
          .grid(row=1, column=2, sticky="w")
        tk.Entry(cfgf, textvariable=self.batch_var,
                 bg="#3e3e3e", fg="white")\
          .grid(row=1, column=3, sticky="ew", padx=5, pady=2)

        # Prompt text areas
        self.text_widgets = {}
        rows = [("System Prompt:",3), ("Screenshot Prompt:",2), ("Commentary Prompt:",3)]
        for i, (lbl, h) in enumerate(rows, start=2):
            tk.Label(cfgf, text=lbl, bg="#2b2b2b", fg="white")\
              .grid(row=i, column=0, sticky="nw", pady=(5,0))
            txt = tk.Text(cfgf, height=h, bg="#3e3e3e", fg="white", wrap="word")
            txt.grid(row=i, column=1, columnspan=4, sticky="ew", padx=5, pady=(5,0))
            self.text_widgets[lbl] = txt

        # Save Settings
        tk.Button(cfgf, text="💾 Save Settings", command=self._on_save,
                  bg="#0066cc", fg="white")\
          .grid(row=5, column=4, sticky="e", pady=(10,0))

        # Preview canvas
        self.preview_canvas = tk.Canvas(self, width=800, height=600, bg="#111")
        self.preview_canvas.pack(pady=5)
        self.preview_img = None
        self._update_preview()

        # Chat display
        self.canvas = tk.Canvas(self, bg="#2b2b2b", highlightthickness=0)
        vsb    = tk.Scrollbar(self, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(fill="both", expand=True, padx=10)
        self.bubble_frame = tk.Frame(self.canvas, bg="#2b2b2b")
        self.canvas.create_window((0,0), window=self.bubble_frame, anchor="nw")
        self.bubble_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        # Input and buttons
        rowf = tk.Frame(self, bg="#2b2b2b")
        rowf.pack(fill="x", padx=10, pady=5)
        self.entry = tk.Entry(rowf, bg="#3e3e3e", fg="white",
                              insertbackground="white", font=("Consolas",12))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.send_message())

        for txt, cmd, col in [
            ("📸 Screenshot", self.send_screenshot, "#00875e"),
            ("Start Auto",    self.toggle_auto,     "#ffaa00"),
            ("Send",          self.send_message,    "#5e00ff"),
        ]:
            b = tk.Button(rowf, text=txt, command=cmd,
                         bg=col, fg="white", padx=8, pady=5)
            b.pack(side="right", padx=5)
            if txt == "Start Auto":
                self.auto_btn = b

        self.status = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self.status,
                 bg="#1f1f1f", fg="white", anchor="w", font=("Consolas",9))\
          .pack(fill="x", side="bottom")

        self._load_profile()

    def _on_mon_change(self):
        idx = int(self.mon_var.get().split(":",1)[0])
        self.cfg["monitor_index"] = idx

    def _on_toggle_rois(self):
        if self.show_rois_var.get():
            self._draw_roi_overlay()
        else:
            for item in self.preview_canvas.find_withtag("roi"):
                self.preview_canvas.delete(item)

    def _update_preview(self):
        with mss.mss() as sct:
            mon   = sct.monitors[self.cfg.get("monitor_index",1)]
            frame = np.array(sct.grab(mon))[...,:3]
        h, w = frame.shape[:2]
        scale = min(800/w, 600/h)
        disp = cv2.resize(frame, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
        png  = cv2.imencode('.png', disp)[1].tobytes()
        self.preview_img = tk.PhotoImage(data=png)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0,0, anchor="nw", image=self.preview_img)
        if self.show_rois_var.get():
            self._draw_roi_overlay()
        self.after(10000, self._update_preview)

    def _draw_roi_overlay(self):
        # remove old ROI rectangles
        for item in self.preview_canvas.find_withtag("roi"):
            self.preview_canvas.delete(item)

        # compute scaling
        with mss.mss() as sct:
            mon = sct.monitors[self.cfg.get("monitor_index",1)]
        real_w, real_h = mon["width"], mon["height"]
        img_w, img_h   = self.preview_img.width(), self.preview_img.height()
        sx, sy = img_w/real_w, img_h/real_h

        for key, roi in self.ocr_rois.items():
            x0 = roi["left"]*sx
            y0 = roi["top"]*sy
            x1 = (roi["left"]+roi["width"])*sx
            y1 = (roi["top"]+roi["height"])*sy
            self.preview_canvas.create_rectangle(
                x0, y0, x1, y1,
                outline="cyan", width=2, tags=("roi", key)
            )
        # bind drag handlers
        self.preview_canvas.tag_bind("roi", "<Button-1>",   self._on_roi_press)
        self.preview_canvas.tag_bind("roi", "<B1-Motion>",  self._on_roi_drag)
        self.preview_canvas.tag_bind("roi", "<ButtonRelease-1>", self._on_roi_release)
        self._drag_data = {"key":None, "x":0, "y":0}

    def _on_roi_press(self, event):
        items = self.preview_canvas.find_withtag("current")
        if not items: return
        key = self.preview_canvas.gettags(items[0])[1]
        self._drag_data.update(key=key, x=event.x, y=event.y)

    def _on_roi_drag(self, event):
        key = self._drag_data["key"]
        if not key: return
        dx = event.x - self._drag_data["x"]
        dy = event.y - self._drag_data["y"]
        self.preview_canvas.move(key, dx, dy)
        with mss.mss() as sct:
            mon = sct.monitors[self.cfg.get("monitor_index",1)]
        sx = mon["width"] / self.preview_img.width()
        sy = mon["height"]/ self.preview_img.height()
        self.ocr_rois[key]["left"] += int(dx/sx)
        self.ocr_rois[key]["top"]  += int(dy/sy)
        self._drag_data.update(x=event.x, y=event.y)

    def _on_roi_release(self, event):
        self._drag_data["key"] = None
        self._draw_roi_overlay()

    def _load_profile(self):
        prof = self.profile_var.get()
        data = load_profile(prof)
        self.text_widgets["System Prompt:"].delete("1.0","end")
        self.text_widgets["System Prompt:"].insert("1.0", data["system"])
        self.text_widgets["Screenshot Prompt:"].delete("1.0","end")
        self.text_widgets["Screenshot Prompt:"].insert("1.0", data["screenshot"])
        self.text_widgets["Commentary Prompt:"].delete("1.0","end")
        self.text_widgets["Commentary Prompt:"].insert("1.0", data["commentary"])
        self.ocr_rois = data.get("ocr_rois", {})

    def _on_save(self):
        self.cfg["selected_profile"]     = self.profile_var.get()
        self.cfg["commentary_interval"]  = float(self.interval_var.get())
        self.cfg["commentary_batch"]     = int(self.batch_var.get())
        save_settings(self.cfg)
        prof = self.profile_var.get()
        save_profile(prof, {
            **load_profile(prof),
            "system":     self.text_widgets["System Prompt:"].get("1.0","end").strip(),
            "screenshot": self.text_widgets["Screenshot Prompt:"].get("1.0","end").strip(),
            "commentary": self.text_widgets["Commentary Prompt:"].get("1.0","end").strip(),
            "ocr_rois":   self.ocr_rois
        })
        self.status.set("Settings saved.")

    def _capture_image_bytes(self):
        """
        Returns (thumb_png, vision_png).
        thumb: 256×256 for OCR/RAG
        vision: resized to ≤896×896 for vision
        """
        with mss.mss() as sct:
            idx   = int(self.cfg.get("monitor_index", 1))
            mon   = sct.monitors[idx]
            frame = np.array(sct.grab(mon))[..., :3]

        thumb = cv2.resize(frame, (256,256), interpolation=cv2.INTER_AREA)
        _, buf_thumb = cv2.imencode('.png', thumb)

        h, w = frame.shape[:2]
        scale = min(896/w, 896/h, 1.0)
        vis = cv2.resize(frame, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
        _, buf_vis = cv2.imencode('.png', vis)

        return buf_thumb.tobytes(), buf_vis.tobytes()

    def _read_ocr(self):
        out = {}
        if not self.ocr_rois:
            return out
        with mss.mss() as sct:
            for key, roi in self.ocr_rois.items():
                img = np.array(sct.grab(roi))[...,:3]
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                _, bw = cv2.threshold(gray,150,255,cv2.THRESH_BINARY)
                txt = pytesseract.image_to_string(bw, config="--psm 6").strip()
                if key == "season" and txt:
                    self.last_season = txt
                else:
                    out[key] = txt
        return out

    def add_bubble(self, text, is_user):
        bg   = "#005f99" if is_user else "#4b0082"
        side = "e" if is_user else "w"
        lbl  = tk.Label(self.bubble_frame, text=text, bg=bg,
                        fg="white", wraplength=400, justify="left",
                        font=("Consolas",11), padx=8, pady=4)
        lbl.pack(anchor=side, pady=5)
        self.canvas.update_idletasks()
        self.canvas.yview_moveto(1.0)

    def send_screenshot(self):
        self.add_bubble("📸 Screenshot sent", True)
        def task():
            self.status.set("Processing…")
            thumb, vis = self._capture_image_bytes()

            # debug save
            try:
                p = os.path.join(os.getcwd(), "debug_snap_vision.png")
                with open(p, "wb") as f:
                    f.write(vis)
                self.add_bubble(f"[DEBUG] Vision snap saved to {p}", False)
            except Exception as e:
                self.add_bubble(f"[DEBUG ERROR saving image: {e}]", False)

            desc = self.lm.send_screenshot_data(
                vis,
                self.text_widgets["System Prompt:"].get("1.0","end").strip(),
                self.text_widgets["Screenshot Prompt:"].get("1.0","end").strip()
            )
            self.add_bubble(f"[DEBUG desc] {desc}", False)

            game_state = self._read_ocr()
            hits       = self.rag.query(desc, top_k=3)
            rag_ctx    = "\n".join(h["text"] for h in hits)
            rag_ctx    = _truncate(rag_ctx, 2000)

            gs_txt     = "\n".join(f"- {k}: {v}" for k,v in game_state.items()) or "None"
            season_line= f"Current season: {self.last_season}" if self.last_season else ""

            tmpl   = self.text_widgets["Commentary Prompt:"].get("1.0","end").strip()
            prompt = tmpl.format(
                rag_context=rag_ctx,
                game_state=gs_txt,
                captures=desc
            )
            if season_line:
                prompt = season_line + "\n\n" + prompt

            self.add_bubble("[DEBUG prompt]\n" + "\n".join(prompt.split("\n")[:6]), False)

            reply = self.lm.chat(
                self.text_widgets["System Prompt:"].get("1.0","end").strip(),
                prompt, temperature=0.7, max_tokens=-1
            )
            self.add_bubble(reply, False)
            self.speak_enqueue(reply)
            self.status.set("Ready")

        threading.Thread(target=task, daemon=True).start()

    def send_message(self):
        self._pause_auto = True
        txt = self.entry.get().strip()
        if not txt:
            self._pause_auto = False
            return
        self.entry.delete(0,"end")
        self.add_bubble(txt, True)

        def task():
            self.status.set("Thinking…")
            reply = self.lm.chat(
                self.text_widgets["System Prompt:"].get("1.0","end").strip(),
                txt, temperature=0.7, max_tokens=-1
            )
            self.add_bubble(reply, False)
            self.speak_enqueue(reply)
            self.status.set("Ready")
            self._pause_auto = False

        threading.Thread(target=task, daemon=True).start()

    def toggle_auto(self):
        self.auto_mode = not self.auto_mode
        self.auto_btn.config(text="Stop Auto" if self.auto_mode else "Start Auto")
        if self.auto_mode:
            threading.Thread(target=self._auto_loop, daemon=True).start()

    def _auto_loop(self):
        captions = []
        while self.auto_mode:
            if self._pause_auto:
                time.sleep(0.1)
                continue

            try:
                self.commentary_interval = float(self.interval_var.get())
                self.commentary_batch    = int(self.batch_var.get())
            except:
                pass

            thumb, vis = self._capture_image_bytes()
            desc = self.lm.send_screenshot_data(
                vis,
                self.text_widgets["System Prompt:"].get("1.0","end").strip(),
                self.text_widgets["Screenshot Prompt:"].get("1.0","end").strip()
            )
            captions.append(desc)

            if len(captions) >= self.commentary_batch:
                game_state = self._read_ocr()
                hits       = self.rag.query(captions[-1], top_k=3)
                rag_ctx    = "\n".join(h["text"] for h in hits)
                rag_ctx    = _truncate(rag_ctx, 2000)

                gs_txt     = "\n".join(f"- {k}: {v}" for k,v in game_state.items()) or "None"
                lines      = _truncate("\n".join(f"{i+1}) {c}" for i,c in enumerate(captions)), 1024)
                season_line= f"Current season: {self.last_season}" if self.last_season else ""

                tmpl   = self.text_widgets["Commentary Prompt:"].get("1.0","end").strip()
                prompt = tmpl.format(
                    rag_context=rag_ctx,
                    game_state=gs_txt,
                    captures=lines
                )
                if season_line:
                    prompt = season_line + "\n\n" + prompt

                self.add_bubble("[DEBUG prompt]\n" + "\n".join(prompt.split("\n")[:6]), False)

                reply = self.lm.chat(
                    self.text_widgets["System Prompt:"].get("1.0","end").strip(),
                    prompt, temperature=0.7, max_tokens=-1
                )
                self.add_bubble(reply, False)
                self.speak_enqueue(reply)
                captions.clear()

            time.sleep(self.commentary_interval)

    def speak_enqueue(self, text: str):
        self._tts_queue.put(text.replace("*",""))

    def _tts_player_loop(self):
        while True:
            txt = self._tts_queue.get()
            try:
                wav_bytes = self.tts.generate_wav(txt)
                tmp       = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp.write(wav_bytes); tmp.flush()
                sa.WaveObject.from_wave_file(tmp.name).play().wait_done()
                tmp.close(); os.unlink(tmp.name)
            except Exception as e:
                self.add_bubble(f"[TTS Error: {e}]", False)
            finally:
                self._tts_queue.task_done()
