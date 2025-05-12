# config.py

import os, json

CONFIG_FILE = "settings.json"
PROFILE_DIR = "profiles"

DEFAULT_SETTINGS = {
    "lmstudio_url":        "http://192.168.0.24:1234",
    "tts_server_url":      "http://192.168.0.24:1235",
    "model_name":          "qwen3-30b-a3b-q4_k_m.gguf",
    "rag_add_url":         "http://192.168.0.24:8000/add",
    "rag_query_url":       "http://192.168.0.24:8000/query",
    "commentary_interval": 5,
    "commentary_batch":    3,
    "show_rois": False,
    "selected_profile":    "Default"
}

def load_settings():
    # 1) load or create settings.json
    if os.path.isfile(CONFIG_FILE):
        try:
            cfg = json.load(open(CONFIG_FILE))
        except:
            cfg = DEFAULT_SETTINGS.copy()
    else:
        cfg = DEFAULT_SETTINGS.copy()

    # fill in any missing defaults
    for k,v in DEFAULT_SETTINGS.items():
        cfg.setdefault(k, v)

    return cfg

def save_settings(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def list_profiles():
    return [f[:-5] for f in os.listdir(PROFILE_DIR) if f.endswith(".json")]

def load_profile(name):
    path = os.path.join(PROFILE_DIR, f"{name}.json")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # return everything, but ensure system/screenshot/commentary exist
    return {
        **data,
        "system":     data.get("system",     ""),
        "screenshot": data.get("screenshot", ""),
        "commentary": data.get("commentary", "")
    }

def save_profile(name, prompts):
    # prompts may include keys beyond system/screenshot/commentary
    path = os.path.join(PROFILE_DIR, f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prompts, f, indent=2)
