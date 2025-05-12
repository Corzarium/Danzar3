# ui/app.py

import os
import threading
import tempfile
import tkinter as tk
import simpleaudio as sa
import keyboard
import mss
import queue
import time
from mss.tools import to_png
from config import (
    load_settings, save_settings,
    load_profile, save_profile, list_profiles
)
from lm_client import LMClient
from rag_client import RAGClient
from tts_client import TTSClient

from ui.widgets import truncate, add_bubble
from ui.preview import PreviewCanvas
from ui.frames import build_config_frame, build_preview_frame, build_chat_frame
from ui.roi_manager import ROIManager


class DanzarAIApp(tk.Tk):
    def __init__(self, cfg, lm: LMClient, rag: RAGClient, tts: TTSClient):
        super().__init__()
        self.cfg = cfg
        self.lm  = lm
        self.rag = rag
        self.tts = tts
        # Queue for text-to-speech playback
        self._tts_queue = queue.Queue()

        # Ensure config defaults
        self.cfg.setdefault("ocr_rois", {})
        self.cfg.setdefault("selected_profile", "")
        self.cfg.setdefault("commentary_interval", 5)
        self.cfg.setdefault("commentary_batch", 1)
        self.cfg.setdefault("monitor_index", 1)

        # Tk Variables — must come before frame building
        self.profile_var   = tk.StringVar(value=self.cfg["selected_profile"])
        self.interval_var  = tk.StringVar(value=str(self.cfg["commentary_interval"]))
        self.batch_var     = tk.StringVar(value=str(self.cfg["commentary_batch"]))
        self.show_rois_var = tk.BooleanVar(value=True)

        # Build monitor list and var
        mons = [f"{i}: {m['width']}x{m['height']}"
                for i, m in enumerate(mss.mss().monitors) if i>0]
        idx = self.cfg["monitor_index"]
        default_mon = next((s for s in mons if s.startswith(f"{idx}:")), mons[0])
        self.mon_var = tk.StringVar(value=default_mon)

        # Window setup
        self.title("Danzar AI")
        self.configure(bg="#2b2b2b")
        self.geometry("800x1000")

        # Build UI sections
        self.config_frame = build_config_frame(self, self)
        self.preview      = build_preview_frame(self, self)
        self.chat_canvas, self.bubble_frame, self.entry, self.auto_btn = build_chat_frame(self, self)

        # Populate prompts for initial profile
        self._load_profile()

        # ROI manager listens for preview updates
        self.roi_mgr = ROIManager(self.preview, self.cfg)
        # Redraw when show_rois toggles
        self.show_rois_var.trace_add("write", lambda *a: self.preview.update_preview())

        # Start background threads
        threading.Thread(target=self._setup_hotkeys, daemon=True).start()
        threading.Thread(target=self._tts_player_loop, daemon=True).start()
        threading.Thread(target=self._commentary_loop, daemon=True).start()
    # ─── Manual Controls ─────────────────────────────────────────────

    def send_screenshot(self):
        """Grab screen → PNG → LM vision call → display."""
        try:
            with mss.mss() as sct:
                mon = sct.monitors[self.cfg["monitor_index"]]
                img = sct.grab(mon)
            png_bytes = to_png(img.rgb, img.size)
            add_bubble(self.bubble_frame, "📸 Screenshot sent", True)

            system = self.text_widgets["System Prompt:"].get("1.0", "end").strip()
            user   = self.text_widgets["Screenshot Prompt:"].get("1.0", "end").strip()
            resp   = self.lm.send_screenshot_data(png_bytes, system, user)
        except Exception as e:
            resp = f"[Screenshot Error: {e}]"

        add_bubble(self.bubble_frame, resp, False)
        # ← enqueue for TTS
        self._tts_queue.put(resp)

        add_bubble(self.bubble_frame, resp, False)

    def _start_record(self):
        self._recording = True
        add_bubble(self.bubble_frame, "🎤 Recording started...", True)
        # TODO: insert microphone capture logic

    def _stop_record(self):
        self._recording = False
        add_bubble(self.bubble_frame, "🎤 Recording stopped", False)
        # TODO: insert stop/transcribe logic

    # ─── UI Callbacks ─────────────────────────────────────────────────

    def _load_profile(self):
        profile = self.profile_var.get()
        data    = load_profile(profile)

        # Remap keys if needed
        if "system" in data:
            data["system_prompt"] = data.pop("system")
        if "screenshot" in data:
            data["screenshot_prompt"] = data.pop("screenshot")
        if "commentary" in data:
            data["commentary_prompt"] = data.pop("commentary")

        self.cfg.update(data)
        for lbl, txt in self.text_widgets.items():
            key = lbl.strip(":").lower().replace(" ", "_")
            txt.delete("1.0", tk.END)
            txt.insert("1.0", self.cfg.get(key, ""))

        self.preview.update_preview()

    def _on_save(self):
        prof = self.profile_var.get()
        base = load_profile(prof)

        updates = {
            "system":        self.text_widgets["System Prompt:"].get("1.0","end").strip(),
            "screenshot":    self.text_widgets["Screenshot Prompt:"].get("1.0","end").strip(),
            "commentary":    self.text_widgets["Commentary Prompt:"].get("1.0","end").strip(),
            "ocr_rois":      self.roi_mgr.rois,
            "monitor_index": int(self.mon_var.get().split(":",1)[0])
        }

        save_profile(prof, { **base, **updates })

        # Also save global settings (interval + batch)
        self.cfg["selected_profile"]    = prof
        self.cfg["monitor_index"]       = updates["monitor_index"]
        self.cfg["commentary_interval"] = float(self.interval_var.get())
        self.cfg["commentary_batch"]    = int(self.batch_var.get())
        save_settings(self.cfg)

        add_bubble(self.bubble_frame, "Settings & ROIs saved ✔️", False)

    def _on_mon_select(self, mon_str):
        idx = int(mon_str.split(":",1)[0])
        self.cfg["monitor_index"] = idx
        self.preview.update_preview()

    def _on_send(self, txt: str):
        txt = txt.strip()
        if not txt:
            return

        # 1) show user bubble
        add_bubble(self.bubble_frame, txt, True)

        # 2) clear the entry field if it still holds this text
        try:
            self.entry.delete(0, tk.END)
        except Exception:
            pass

        # 3) perform the LLM call
        system = self.text_widgets["System Prompt:"].get("1.0", "end").strip()
        try:
            resp = self.lm.chat(system, txt)
        except Exception as e:
            resp = f"[Chat Error: {e}]"

        # 4) display the AI response
        add_bubble(self.bubble_frame, resp, False)
        self._tts_queue.put(resp)

    def _toggle_commentary(self):
        self.auto_mode = not getattr(self, "auto_mode", False)
        self.auto_btn.config(text="Stop Commentary" if self.auto_mode else "Commentary Mode")

    # ─── Background Workers ───────────────────────────────────────────

    def _setup_hotkeys(self):
        keyboard.add_hotkey('F2', lambda: self.send_screenshot())
        keyboard.add_hotkey('F3', lambda: (
            self._start_record() if not getattr(self, "_recording", False)
            else self._stop_record()
        ))
        keyboard.add_hotkey('F4', lambda: self._toggle_commentary())
        add_bubble(self.bubble_frame,
                   "🎮 Hotkeys: F8=Screenshot, F9=Mic, F10=Commentary",
                   False)

    def _tts_player_loop(self):
        while True:
            txt = self._tts_queue.get()
            try:
                wav_bytes = self.tts.generate_wav(txt)
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp.write(wav_bytes); tmp.flush(); tmp.close()
                sa.WaveObject.from_wave_file(tmp.name).play().wait_done()
                os.unlink(tmp.name)
            except Exception as e:
                add_bubble(self.bubble_frame, f"[TTS Error: {e}]", False)
            finally:
                self._tts_queue.task_done()

    def _commentary_loop(self):
        """
        While auto_mode is True, send a batch of screenshots/commentaries
        every commentary_interval seconds, then repeat.
        """
        while True:
            if getattr(self, "auto_mode", False):
                # read current settings
                try:
                    interval = float(self.interval_var.get())
                except ValueError:
                    interval = 5.0
                try:
                    batch = int(self.batch_var.get())
                except ValueError:
                    batch = 1

                for i in range(batch):
                    if not self.auto_mode:
                        break
                    self.send_screenshot()
                    time.sleep(interval)
            else:
                # avoid busy‐spin when commentary is off
                time.sleep(0.2)

    def _run_batch(self):
        """
        Send `batch` screenshots at `interval` seconds apart,
        collect their vision descriptions, then call chat() once
        with all of them as context.
        """
        def worker(batch, interval):
            add_bubble(self.bubble_frame,
                       f"🚀 Capturing {batch} screenshots every {interval}s for batch…",
                       False)

            system_prompt = self.text_widgets["System Prompt:"].get("1.0","end").strip()
            commentary_tpl = self.text_widgets["Commentary Prompt:"].get("1.0","end").strip()

            descriptions = []
            for i in range(batch):
                # 1) grab & send screenshot to vision
                try:
                    with mss.mss() as sct:
                        mon = sct.monitors[self.cfg["monitor_index"]]
                        img = sct.grab(mon)
                    png_bytes = to_png(img.rgb, img.size)
                    desc = self.lm.send_screenshot_data(
                        png_bytes,
                        system_prompt,
                        self.text_widgets["Screenshot Prompt:"].get("1.0","end").strip()
                    )
                except Exception as e:
                    desc = f"[Vision Error: {e}]"
                add_bubble(self.bubble_frame, f"[Capture {i+1}] {desc}", False)
                descriptions.append(desc)

                # wait before the next, unless it’s the last one
                if i < batch - 1:
                    time.sleep(interval)

            # 2) build one combined user prompt
            # e.g. inject all captures into your commentary template
            combined_captures = "\n\n".join(
                f"Capture {i+1}: {d}" for i,d in enumerate(descriptions)
            )
            user_prompt = commentary_tpl.replace("{captures}", combined_captures)

            # 3) single chat call
            try:
                reply = self.lm.chat(system_prompt, user_prompt)
            except Exception as e:
                reply = f"[Chat Error: {e}]"

            # 4) display + TTS enqueue
            add_bubble(self.bubble_frame, reply, False)
            self._tts_queue.put(reply)
            add_bubble(self.bubble_frame, "✅ Batch commentary complete", False)

        # parse the spinbox values
        try:
            interval = float(self.interval_var.get())
        except ValueError:
            interval = 1.0
        try:
            batch = int(self.batch_var.get())
        except ValueError:
            batch = 1

        threading.Thread(target=worker, args=(batch, interval), daemon=True).start()



def main():
    cfg = load_settings()

    lm = LMClient(
        base_url   = cfg["lmstudio_url"].rstrip("/") + "/v1",
        api_key    = cfg.get("lmstudio_api_key", ""),
        model_name = cfg["model_name"]
    )
    rag = RAGClient(
        add_url   = cfg["rag_add_url"],
        query_url = cfg["rag_query_url"]
    )
    tts = TTSClient(cfg["tts_server_url"])

    app = DanzarAIApp(cfg, lm, rag, tts)
    try:
        app.mainloop()
    finally:
        save_settings(cfg)


if __name__ == "__main__":
    main()
