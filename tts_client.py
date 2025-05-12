# tts_client.py

import requests

class TTSClient:
    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def generate_wav(self, text: str) -> bytes:
        """
        Send text to the AI server's /tts endpoint and return raw WAV bytes.
        """
        resp = requests.post(
            f"{self.url}/tts",
            json={"text": text},
            timeout=60
        )
        resp.raise_for_status()
        return resp.content
