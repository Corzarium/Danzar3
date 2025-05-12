#!/usr/bin/env python3
import sys
import os
import queue
import base64
import keyboard
import simpleaudio as sa
import tkinter as tk
import requests                    # ← for /v1/models check
import mss
from mss.tools import to_png
from uuid import uuid4
from PIL import Image

from config         import load_settings, save_settings
from lm_client      import LMClient
from rag_client     import RAGClient
from tts_client     import TTSClient
from ui.widgets     import add_bubble
from ui.frames      import build_config_frame, build_preview_frame, build_chat_frame
from ui.preview     import PreviewCanvas
from ui.roi_manager import ROIManager

class DanzarAIApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DanzarAI")
        self.geometry("1000x700")

        # Load settings + profile
        self.cfg = load_settings()
        print(f"🛠 [DEBUG] Loaded settings.json, model_name = '{self.cfg.get('model_name')}'")

        # Check what LM Studio knows about your models
        try:
            resp = requests.get(f"{self.cfg['lmstudio_url'].rstrip('/')}/v1/models")
            data = resp.json()
            available = [m['id'] for m in data.get('data', [])]
            print("🛠 [DEBUG] LM Studio registered models:", available)
        except Exception as e:
            print("🛠 [DEBUG] Error fetching /v1/models:", e)

        (self.config_canvas,
         self.config_frame,
         self.monitor_var,
         self.profile_var,
         self.profile_data) = build_config_frame(self, self.cfg)

        # Preview + ROI
        self.preview_canvas, self.preview_frame = build_preview_frame(self, self)
        self.preview = PreviewCanvas(self.preview_canvas, self)
        self.roi_mgr = ROIManager(
            self.preview_canvas,
            self.profile_data.get("ocr_rois", {})
        )

        # Chat + toolbar
        (self.chat_canvas,
         self.bubble_frame,
         self.entry,
         self.send_btn,
         self.screenshot_btn,
         self.mic_btn,
         self.auto_btn,
         self.batch_btn) = build_chat_frame(self, self)

        # Wire toolbar buttons
        self.send_btn    .config(command=self._on_send_click)
        self.screenshot_btn.config(command=self._take_screenshot)
        self.auto_btn    .config(command=self._toggle_commentary)
        self.batch_btn   .config(command=self._run_batch)

        # Instantiate clients
        self.lm  = LMClient(
            self.cfg["lmstudio_url"],
            "",  # API key slot unused
            self.cfg["model_name"]
        )
        self.rag = RAGClient(
            self.cfg["rag_add_url"],
            self.cfg["rag_query_url"]
        )
        self.tts = TTSClient(self.cfg["tts_server_url"])

        # Internal state
        self.commentary_enabled = False
        self.batch_size         = self.profile_data.get("commentary_batch", 3)
        self.screenshot_queue   = queue.Queue()

        # Hotkeys for screenshots & commentary
        keyboard.add_hotkey('ctrl+f2', self._take_screenshot)
        keyboard.add_hotkey('ctrl+f3', self._toggle_commentary)
        keyboard.add_hotkey('ctrl+f4', self._run_batch)

        # Clean shutdown
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_send_click(self):
        text = self.entry.get().strip()
        if not text:
            return
        add_bubble(self.bubble_frame, text, is_user=True)
        self.entry.delete(0, tk.END)
        self._chat_exchange([], prompt=text)

    def _take_screenshot(self):
        m_index = self.monitor_var.get()
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[m_index])
            raw_png = to_png(shot.rgb, shot.size)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            img.save("test.png")

            # Preview display
            pil_img = Image.frombytes('RGB', shot.size, shot.rgb)
            self.preview.show_image(pil_img)

            # Queue & send
            self.screenshot_queue.put(raw_png)
            if not self.commentary_enabled:
                self._chat_exchange([raw_png])

    def _toggle_commentary(self):
        self.commentary_enabled = not self.commentary_enabled
        status = "ON" if self.commentary_enabled else "OFF"
        add_bubble(self.bubble_frame, f"Commentary: {status}", is_user=False)

    def _run_batch(self):
        imgs = []
        while not self.screenshot_queue.empty() and len(imgs) < self.batch_size:
            imgs.append(self.screenshot_queue.get())
        if imgs:
            self._chat_exchange(imgs)

    def _chat_exchange(self, images, prompt=None):
        """
        Routes screenshot inputs through send_screenshot_data (with deep debug)
        and text-only via chat().
        """
        # Determine prompts
        if images:
            system_p = self.profile_data.get(
                "screenshot_system_prompt",
                "You are analyzing game screenshots."
            )
            user_p = prompt or self.profile_data.get(
                "screenshot_prompt",
                "Describe what you see."
            )
        else:
            system_p = self.profile_data.get(
                "system_prompt",
                "You are a helpful game commentary assistant."
            )
            user_p = prompt or ""

        # Optional RAG ingest/query
        try:
            self.rag.add_and_query({"prompt": user_p, "images": images})
        except Exception:
            pass

        if images:
            replies = []
            for png in images:
                # --- DEBUG LOGGING ---
                b64 = base64.b64encode(png).decode("utf-8")
                print("🔍 [DEBUG] Preparing to send_screenshot_data:")
                print("    system_p:", system_p)
                print("    user_p:", user_p)
                print("    image data length:", len(b64))
                print("    base64 prefix:", b64[:200])
                # --- end debug ---

                reply = self.lm.send_screenshot_data(png, system_p, user_p)
                replies.append(reply)
            response = "\n\n".join(replies)
        else:
            response = self.lm.chat(system_p, user_p)

        # Display and speak
        add_bubble(self.bubble_frame, response, is_user=False)
        wav = self.tts.generate_wav(response)
        sa.play_buffer(wav, 1, 2, 22050)

    def _on_close(self):
        # Save GUI state
        self.cfg["monitor_index"]    = self.monitor_var.get()
        self.cfg["selected_profile"] = self.profile_var.get()
        save_settings(self.cfg)
        self.destroy()

def main():
    app = DanzarAIApp()
    app.mainloop()

if __name__ == "__main__":
    main()
