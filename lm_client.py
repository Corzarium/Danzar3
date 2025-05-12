# lm_client.py

import base64
from pathlib import Path
from openai import OpenAI
import json
import requests

class LMClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key   = api_key
        self.model     = model

    def chat(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt}
            ]
        }
        print(f"[LLM CHAT DEBUG] → POST {url}")
        print(f"[LLM CHAT DEBUG]   JSON={json.dumps(body)[:200]}…")
        try:
            resp = requests.post(url, json=body, timeout=15)
            print(f"[LLM CHAT DEBUG] ← {resp.status_code} {resp.text[:200]!r}")
            resp.raise_for_status()
        except Exception as e:
            print(f"[LLM CHAT DEBUG] Exception: {type(e).__name__}: {e}")
            raise
        return resp.json()["choices"][0]["message"]["content"]

    def send_screenshot_from_file(self, file_path: str,
                                  system_prompt: str,
                                  user_prompt: str) -> str:
        # legacy: we still keep this if you want exact full-res via disk
        path = Path(file_path)
        raw  = path.read_bytes()
        return self.send_screenshot_data(raw, system_prompt, user_prompt)

    def send_screenshot_data(self, png_bytes: bytes, system_prompt: str, user_prompt: str) -> str:
        url = f"{self.base_url}/v1/chat/completions"
        b64 = base64.b64encode(png_bytes).decode()
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt}
            ],
            "images": [
                {"mime_type": "image/png", "data": b64}
            ]
        }
        print(f"[LLM IMG DEBUG] → POST {url}")
        print(f"[LLM IMG DEBUG]   JSON keys={list(body.keys())}, img_bytes={len(png_bytes)}")
        try:
            resp = requests.post(url, json=body, timeout=30)
            print(f"[LLM IMG DEBUG] ← {resp.status_code} {resp.text[:200]!r}")
            resp.raise_for_status()
        except Exception as e:
            print(f"[LLM IMG DEBUG] Exception: {type(e).__name__}: {e}")
            raise
        return resp.json()["choices"][0]["message"]["content"]
