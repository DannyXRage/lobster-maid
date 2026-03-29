import os
import time
import json
import random
import threading
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import memory
import tools  # noqa: F401 - auto-register all tool modules
from tool_calling_loop import chat_with_tools

# ── Config ──────────────────────────────────────────
BUSY = False
TG_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
OR_KEY = os.environ["OPENROUTER_API_KEY"]
API_KEY = os.environ.get("LOBSTER_API_KEY", "")
TG_API = "https://api.telegram.org/bot" + TG_TOKEN
STATS_FILE = "/app/stats.json"

SYSTEM_PROMPT = (
    "You are LobsterMaid, a helpful and concise assistant. "
    "Reply in the same language the user writes in. "
    "Keep answers brief and to the point unless the user asks for detail."
)

# ── Model Tiers ─────────────────────────────────────
# T1: 主力（每次随机排序，分散负载）
TIER1 = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "arcee-ai/trinity-large-preview:free",
    "google/gemma-3-12b-it:free",
]
# T2: 海外备选（固定顺序）
TIER2 = [
    "arcee-ai/trinity-mini:free",
    "nvidia/nemotron-nano-12b-v2-vl:free",
    "google/gemma-3n-e4b-it:free",
    "nvidia/nemotron-nano-9b-v2:free",
    "google/gemma-3n-e2b-it:free",
]
# T3: 中国兜底
TIER3_CN = ["z-ai/glm-4.5-air:free"]
# T4: 超小模型最后保底
TIER4_MICRO = [
    "liquid/lfm-2.5-1.2b-instruct:free",
    "liquid/lfm-2.5-1.2b-thinking:free",
]

def get_model_order():
    t1 = TIER1.copy()
    random.shuffle(t1)
    return t1 + TIER2 + TIER3_CN + TIER4_MICRO

def short_name(model):
    return model.split("/")[-1].replace(":free", "")


# 支持 OpenAI function calling 的模型集合
# 不在此集合中的模型调用时不传 tools 参数，走普通对话
TOOL_CAPABLE = {
    "google/gemma-3-12b-it:free",
    "z-ai/glm-4.5-air:free",
    # 新模型需实际测试确认后再加入
}


# ── Stats (持久化 JSON, total 永不清零) ──────────────
def load_stats():
    try:
        with open(STATS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"total": {}, "current": {}, "t0": time.time()}

def save_stats(s):
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(s, f)
    except Exception as e:
        print(f"save_stats err: {e}", flush=True)

def record(model, success):
    s = load_stats()
    key = "ok" if success else "fail"
    for period in ("total", "current"):
        s[period].setdefault(model, {"ok": 0, "fail": 0})[key] += 1
    save_stats(s)

def format_stats():
    s = load_stats()
    uptime = time.time() - s.get("t0", time.time())
    days = int(uptime // 86400)
    hours = int((uptime % 86400) // 3600)
    total_req = sum(v["ok"] + v["fail"] for v in s["total"].values())
    lines = [
        f"📊 LobsterMaid Stats",
        f"运行: {days}天{hours}小时 | 总请求: {total_req}",
        "", "--- 累计 (total, 永不清零) ---",
    ]
    for m, v in sorted(s["total"].items(), key=lambda x: -x[1]["ok"]):
        rate = v["ok"] / max(v["ok"] + v["fail"], 1) * 100
        lines.append(f"  {short_name(m)}: ✅{v['ok']} ❌{v['fail']} ({rate:.0f}%)")
    if s["current"]:
        cur_req = sum(v["ok"] + v["fail"] for v in s["current"].values())
        lines += ["", f"--- 当期 (可清零) | 请求: {cur_req} ---"]
        for m, v in sorted(s["current"].items(), key=lambda x: -x[1]["ok"]):
            rate = v["ok"] / max(v["ok"] + v["fail"], 1) * 100
            lines.append(f"  {short_name(m)}: ✅{v['ok']} ❌{v['fail']} ({rate:.0f}%)")
    lines += ["", f"T1: {', '.join(short_name(m) for m in TIER1)}"]
    return "\n".join(lines)

def reset_current():
    s = load_stats()
    s["current"] = {}
    save_stats(s)


# ── LLM (分层 fallback) ────────────────────────────
def build_messages(prompt, chat_id=None):
    """从用户输入和记忆上下文构建消息列表"""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if chat_id:
        summary = memory.get_stage_summary(str(chat_id))
        if summary:
            messages.append({"role": "system", "content": f"[Stage Summary]\n{summary}"})
        window = memory.get_sliding_window(str(chat_id))
        messages.extend(window)
    messages.append({"role": "user", "content": prompt})
    return messages


def call_llm(messages, tools=None):
    """
    调用 LLM（带 fallback 链）。
    参数:
        messages: 完整消息列表
        tools: OpenAI 格式的工具定义列表（可选）
    返回: (message_dict, status_string)
        message_dict 包含 content 和/或 tool_calls
    """
    headers = {
        "Authorization": f"Bearer {OR_KEY}",
        "Content-Type": "application/json",
    }
    tried = []
    for model in get_model_order():
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.6,
        }
        if tools and model in TOOL_CAPABLE:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers, json=payload, timeout=60,
            )
            if r.status_code in (429, 404, 400):
                print(f"{r.status_code} on {model}", flush=True)
                record(model, False)
                tried.append(short_name(model))
                continue
            r.raise_for_status()
            record(model, True)
            used = short_name(model)
            print(f"ok: {model}", flush=True)
            skip = f" (skip: {', '.join(tried)})" if tried else ""
            status = f"\n\n🤖 {used}{skip}"
            return r.json()["choices"][0]["message"], status
        except Exception as e:
            print(f"exc on {model}: {e}", flush=True)
            record(model, False)
            tried.append(short_name(model))
    raise Exception("all models exhausted")


# ── Telegram ────────────────────────────────────────
def tg_get(offset=None):
    params = {"timeout": 30}
    if offset is not None:
        params["offset"] = offset
    r = requests.get(f"{TG_API}/getUpdates", params=params, timeout=40)
    r.raise_for_status()
    return r.json()

def tg_send(text):
    try:
        requests.post(
            f"{TG_API}/sendMessage",
            data={"chat_id": CHAT_ID, "text": text}, timeout=10,
        )
    except Exception as e:
        print(f"tg_send fail: {e}", flush=True)


# ── HTTP API (POST /ask + GET /stats + GET /health) ─
class APIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/ask":
            return self._json(404, {"error": "not found"})
        auth = self.headers.get("Authorization", "")
        if API_KEY and auth != f"Bearer {API_KEY}":
            return self._json(401, {"error": "unauthorized"})
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        prompt = body.get("prompt", "").strip()
        if not prompt:
            return self._json(400, {"error": "empty prompt"})
        try:
            messages = build_messages(prompt)
            reply, status = chat_with_tools(call_llm, messages)
            self._json(200, {"reply": reply, "model": status.strip()})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def do_GET(self):
        if self.path == "/stats":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(format_stats().encode())
        elif self.path == "/health":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "not found"})

    def _json(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode())

    def log_message(self, *args):
        pass


# ── Main ────────────────────────────────────────────
def main():
    global BUSY
    print("booting v2...", flush=True)

    # 启动时清空 Telegram 积压的旧消息（防止重启后第一条消息丢失）
    try:
        flush = requests.get(
            f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
            params={"offset": -1}, timeout=10
        ).json()
        if flush.get("result"):
            last_id = flush["result"][-1]["update_id"]
            requests.get(
                f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates",
                params={"offset": last_id + 1}, timeout=10
            )
            print(f"flushed updates up to {last_id}", flush=True)
        else:
            print("no pending updates to flush", flush=True)
    except Exception as e:
        print(f"flush failed: {e}", flush=True)

    threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", 8080), APIHandler).serve_forever(),
        daemon=True,
    ).start()
    print("HTTP API on :8080", flush=True)

    tg_send("🦞 LobsterMaid v2 online")
    offset = None
    data = tg_get()
    if data.get("result"):
        offset = data["result"][-1]["update_id"] + 1

    while True:
        try:
            data = tg_get(offset)
            print(f"poll: {len(data.get('result', []))} updates", flush=True)
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                print(f"upd: id={upd['update_id']} keys={list(upd.keys())}", flush=True)
                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    print("skip: no msg", flush=True)
                    continue
                if str(msg["chat"]["id"]) != str(CHAT_ID):
                    print(f"skip: wrong chat {msg['chat']['id']}", flush=True)
                    continue
                if msg.get("from", {}).get("is_bot"):
                    print("skip: is_bot", flush=True)
                    continue
                text = (msg.get("text") or "").strip()
                if not text or (not text.startswith("?") and not text.startswith("？")):
                    print(f"skip: not cmd text='{text[:30]}'", flush=True)
                    continue
                cmd = text[1:].strip()
                print(f"msg: {text[:50]}", flush=True)
                # Special commands
                if cmd == "s":
                    tg_send(format_stats())
                    continue
                if cmd == "sr":
                    reset_current()
                    tg_send("当期统计已清零（累计不变）")
                    continue
                if cmd == "mr":
                    memory.clear_memory(str(msg["chat"]["id"]))
                    tg_send("记忆已清空（滑动窗口 + 阶段摘要）")
                    continue
                if cmd == "mi":
                    info = memory.get_memory_info(str(msg["chat"]["id"]))
                    tg_send(info)
                    continue

                # Normal LLM query
                if BUSY:
                    continue
                BUSY = True
                try:
                    cid = str(msg["chat"]["id"])
                    tg_send("🦞💭...")
                    memory.add_user_message(cid, cmd)
                    messages = build_messages(cmd, chat_id=cid)
                    reply, status = chat_with_tools(call_llm, messages)
                    memory.add_assistant_message(cid, reply)
                    tg_send(reply[:3400] + status)
                    print(f"reply sent, BUSY={BUSY}", flush=True)
                finally:
                    BUSY = False
        except Exception as e:
            print(f"err: {e}", flush=True)
            time.sleep(2)
            BUSY = False


if __name__ == "__main__":
    main()
