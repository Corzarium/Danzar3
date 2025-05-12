#!/usr/bin/env python3

import sys, os, threading, tempfile, time
import queue, base64, uuid
import tkinter as tk
import simpleaudio as sa
import keyboard
import mss
from uuid import uuid4
from mss.tools import to_png

from config     import load_settings, save_settings
from lm_client  import LMClient
from rag_client import RAGClient
from tts_client import TTSClient
from ui.widgets import add_bubble
from ui.preview import PreviewCanvas
from ui.frames  import build_config_frame, build_preview_frame, build_chat_frame
from ui.roi_manager import ROIManager

class DanzarAIApp(tk.Tk):
    def __init__(self, cfg, lm: LMClient, rag: RAGClient, tts: TTSClient):
        super().__init__()
        # —–––––––––––––––––––––––––––––––––––––––––––
        # Create the StringVar that build_config_frame expects
        # You can seed it from your config if you have a default profile name
        self.profile_var = tk.StringVar(
            value=self.cfg.get("active_profile", "") if hasattr(self, "cfg") else "")
            # define the IntVar for monitor selection
        self.mon_var = tk.IntVar(
            value=cfg.get("monitor_index", 1))
        # commentary interval input
        self.interval_var = tk.IntVar(  value=cfg.get("commentary_interval", 5))
        # you may also need batch size if you have one
        self.batch_var    = tk.IntVar(  value=cfg.get("commentary_batch", 3))
            # if you have other text widgets:
        for label, txt in self.text_widgets.items():
            key = label.rstrip(":").lower().replace(" ", "_")
            cfg[key] = txt.get("1.0","end").strip()
            # write out to disk
        from config import save_settings
        save_settings(cfg)
        add_bubble(self.bubble_frame, "⚙️ Settings saved!", False)
        # bind it as a method so frames.py can see it
        self._on_save = _on_save
        # —–––––––––––––––––––––––––––––––––––––––––
        # —–––––––––––––––––––––––––––––––––––––––––––
        self.cfg  = cfg
        self.lm   = lm
        self.rag  = rag
        self.tts  = tts
        self._tts_queue = queue.Queue()

        # keep the last few turns in memory
        self.chat_history = []

        # … your existing UI setup …
        self.config_frame = build_config_frame(self, self)
        self.preview      = build_preview_frame(self, self)
        self.chat_canvas, self.bubble_frame, self.entry, self.auto_btn = build_chat_frame(self, self)
        self.roi_mgr = ROIManager(self.preview, self.cfg)

        # start threads
        threading.Thread(target=self._setup_hotkeys, daemon=True).start()
        threading.Thread(target=self._tts_player_loop, daemon=True).start()
        threading.Thread(target=self._commentary_loop, daemon=True).start()

    def _index_chat(self, text:str, role:str):
        """Add user or assistant text into RAG store as a long-term memory."""
        # generate a stable UUID for each doc
        doc_id = f"{role}_{uuid.uuid4()}"
        payload = {
            "id":       doc_id,
            "text":     text,
            "metadata": {"role": role}
        }
        try:
            # assuming your RAG server accepts {"id","text","metadata"} on add_url
            self.rag.add_text(payload)
        except Exception as e:
            add_bubble(self.bubble_frame, f"[RAG‐Index Error: {e}]", False)

    def _get_relevant_memories(self, query:str, top_k:int=5):
        """Fetch back the most relevant past docs for this query."""
        try:
            results = self.rag.query(query, top_k=top_k)
            # each result is expected {"text":..., "metadata":...}
            return [r["text"] for r in results]
        except Exception as e:
            add_bubble(self.bubble_frame, f"[RAG‐Query Error: {e}]", False)
            return []

       # When the user sends text:
    def _on_send(self, txt: str):
       txt = txt.strip()
       if not txt:
           return

       # — Show & index user message
       add_bubble(self.bubble_frame, txt, True)
       user_id = f"user_{uuid4()}"
       self.rag.add_text({"id":user_id, "text":txt, "metadata":{"role":"user"}})
       self.chat_history.append({"role":"user","content":txt})

       # — Retrieve top‐3 related memories
       mems = [r["text"] for r in self.rag.query(txt, top_k=3)]

       # — Build prompt: past mems + recent chat history
       prompt = ""
       if mems:
           prompt += "### Remembered:\n" + "\n".join(mems) + "\n\n"
       prompt += "\n".join(
           f"{m['role'].capitalize()}: {m['content']}"
           for m in self.chat_history[-4:]
       )
       prompt += f"\nUser: {txt}"

       # — LLM call
       system = self.text_widgets["System Prompt:"].get("1.0","end").strip()
       resp = self.lm.chat(system, prompt)

       # — Show & index assistant reply
       add_bubble(self.bubble_frame, resp, False)
       assist_id = f"assistant_{uuid4()}"
       self.rag.add_text({"id":assist_id, "text":resp, "metadata":{"role":"assistant"}})
       self.chat_history.append({"role":"assistant","content":resp})
       self._tts_queue.put(resp)

    def send_screenshot(self):
            # … grab PNG bytes into `png_bytes` …
        desc = self.lm.send_screenshot_data(png_bytes,
                                        system_prompt,
                                        screenshot_prompt)
        add_bubble(self.bubble_frame, desc, False)

         # index the image + its caption
        img_id = f"img_{uuid4()}"
        b64   = base64.b64encode(png_bytes).decode()
        self.rag.add_image(img_id, b64, desc)
        """Grab screen → PNG → vision call → display & index"""
        try:
            with mss.mss() as sct:
                mon = sct.monitors[self.cfg["monitor_index"]]
                img = sct.grab(mon)
            png_bytes = to_png(img.rgb, img.size)
            add_bubble(self.bubble_frame, "📸 Screenshot sent", True)

            # retrieve relevant memories based on last chat
            last_user = self.chat_history[-1]["content"] if self.chat_history else ""
            mems = self._get_relevant_memories(last_user, top_k=3)

            system = self.cfg.get("system_prompt","")
            user   = self.cfg.get("screenshot_prompt","")
            # build the same combined style prompt
            prompt = ""
            if mems:
                prompt += "### Remembered:\n" + "\n".join(mems) + "\n\n"
            prompt += user

            resp = self.lm.send_screenshot_data(png_bytes, system, prompt)
        except Exception as e:
            resp = f"[Screenshot Error: {e}]"

        # display + index
        add_bubble(self.bubble_frame, resp, False)
        self.rag.add_image(str(uuid.uuid4()), base64.b64encode(png_bytes).decode(), resp)
        self._tts_queue.put(resp)

    # … keep your other methods (_tts_player_loop, _commentary_loop, etc.) unchanged …

def main():
    cfg = load_settings()
    lm  = LMClient(cfg["lmstudio_url"].rstrip("/"),
                   cfg.get("lmstudio_api_key",""), cfg["model_name"])
    rag = RAGClient(add_url   = cfg["rag_add_url"],
                    query_url = cfg["rag_query_url"])
    tts = TTSClient(cfg["tts_server_url"])
    app = DanzarAIApp(cfg, lm, rag, tts)
    try:
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)
    finally:
        save_settings(cfg)

if __name__ == "__main__":
    main()
