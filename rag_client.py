# rag_client.py

import requests
import json

class RAGClient:
    def __init__(self, add_url: str, query_url: str):
        self.add_url   = add_url
        self.query_url = query_url

    def add_text(self, payload: dict):
        resp = requests.post(self.add_url, json=payload, timeout=30)
        resp.raise_for_status()

    def add_image(self, id: str, b64_png: str, caption: str):
        resp = requests.post(
            self.add_url,
            json={"image": b64_png, "caption": caption},
            timeout=30
        )
        resp.raise_for_status()

    def query(self, query_text: str, top_k: int = 5) -> list[dict]:
        payload = {"query": query_text}
        print(f"[RAG DEBUG] → POST {self.query_url}  payload={json.dumps(payload)}")
        try:
            resp = requests.post(self.query_url, json=payload, timeout=10)
            print(f"[RAG DEBUG] ← {resp.status_code}  body={resp.text[:200]!r}")
            resp.raise_for_status()
        except Exception as e:
            print(f"[RAG DEBUG] Exception: {e}")
            raise

        data = resp.json()
        sources = data.get("sources", [])
        return [
            {"text": s["text"], "metadata":{"type":s["type"],"score":s.get("score",0)}}
            for s in sources[:top_k]
        ]
