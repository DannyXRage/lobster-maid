import os
import json
import time

MEMORY_DIR = "/app/data/memory"
MAX_TURNS = 5
MAX_WINDOW_CHARS = 4000
MAX_SUMMARY_CHARS = 1500

def _ensure_dir():
    os.makedirs(MEMORY_DIR, exist_ok=True)

def _filepath(chat_id):
    return os.path.join(MEMORY_DIR, f"{chat_id}.json")

def _load(chat_id):
    _ensure_dir()
    fp = _filepath(chat_id)
    try:
        with open(fp) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data.setdefault("history", [])
    data.setdefault("stage_summary", "")
    return data

def _save(chat_id, data):
    _ensure_dir()
    fp = _filepath(chat_id)
    try:
        with open(fp, "w") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        print(f"memory save err: {e}", flush=True)

def add_user_message(chat_id, content):
    data = _load(chat_id)
    data["history"].append({"role": "user", "content": content, "ts": time.time()})
    _save(chat_id, data)

def add_assistant_message(chat_id, content):
    data = _load(chat_id)
    data["history"].append({"role": "assistant", "content": content, "ts": time.time()})
    _save(chat_id, data)

def get_sliding_window(chat_id):
    data = _load(chat_id)
    history = data["history"]
    pairs = []
    i = len(history) - 1
    while i >= 0 and len(pairs) < MAX_TURNS:
        if history[i]["role"] == "assistant" and i > 0 and history[i-1]["role"] == "user":
            pairs.append((history[i-1], history[i]))
            i -= 2
        elif history[i]["role"] == "user":
            i -= 1
        else:
            i -= 1
    pairs.reverse()
    messages = []
    for user_msg, asst_msg in pairs:
        messages.append({"role": "user", "content": user_msg["content"]})
        messages.append({"role": "assistant", "content": asst_msg["content"]})
    while messages and sum(len(m["content"]) for m in messages) > MAX_WINDOW_CHARS:
        messages = messages[2:] if len(messages) >= 2 else []
    return messages

def get_stage_summary(chat_id):
    data = _load(chat_id)
    return data.get("stage_summary", "")

def set_stage_summary(chat_id, summary):
    data = _load(chat_id)
    data["stage_summary"] = summary[:MAX_SUMMARY_CHARS]
    _save(chat_id, data)

def clear_memory(chat_id):
    data = {"history": [], "stage_summary": ""}
    _save(chat_id, data)

def get_memory_info(chat_id):
    data = _load(chat_id)
    total_msgs = len(data["history"])
    window = get_sliding_window(chat_id)
    window_chars = sum(len(m["content"]) for m in window)
    has_summary = bool(data.get("stage_summary"))
    return (
        f"Memory: {total_msgs} msgs total, "
        f"window: {len(window)//2} turns ({window_chars} chars), "
        f"summary: {'yes' if has_summary else 'no'}"
    )