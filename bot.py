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

# 回复语言模式：默认英文，?chinese on 切中文
CHINESE_MODE = {}

# 语言规则模板（英文默认 / 中文模式）
LANG_RULE_EN = "LANGUAGE RULE: Reply in ENGLISH by default. Even if the user writes in Chinese, reply in English."
LANG_RULE_CN = "LANGUAGE RULE: Reply in CHINESE (中文) by default. Even if the user writes in English, reply in Chinese."

SYSTEM_PROMPT = (
    "You are LobsterMaid, a helpful and concise assistant. "
    "Keep answers brief and to the point unless the user asks for detail.\n\n"
    "You have access to a web search tool. When you need current or real-time information (today's weather, latest news, current prices, live scores, recent events, etc.), respond with ONLY this tag on a single line:\n"
    "[SEARCH: your search query]\n\n"
    "Rules:\n"
    "- Use [SEARCH] whenever the user asks about time-sensitive or current information\n"
    "- Do NOT guess or fabricate real-time data like weather, news, or prices\n"
    "- After receiving search results, answer naturally based on the data\n"
    "- When presenting search results, ALWAYS include source URLs so the user can verify. Format: mention the fact then put the URL in parentheses or as a numbered reference\n"
    "- Example format: \"According to Reuters, ... (https://reuters.com/...)\" or use numbered references like [1] https://...\n"
    "- {LANG_RULE}\n"
    "- Search query language rules are separate from reply language — always follow the search language rules above regardless of reply language\n"
    "- IMPORTANT: Write search queries in ENGLISH by default for better results, EXCEPT for China-specific topics (Chinese local weather, Chinese news, Chinese addresses, Chinese celebrities) which should use Chinese\n"
    "- Examples:\n"
    "  - \"湖人比赛结果\" → [SEARCH: Lakers latest game result 2026]\n"
    "  - \"比特币价格\" → [SEARCH: Bitcoin price today]\n"
    "  - \"今天上海天气\" → [SEARCH: 上海天气预报 今天]  (China-specific → Chinese)\n"
    "  - \"最近有什么大新闻\" → [SEARCH: latest world news today]\n"
    "  - \"故宫开放时间\" → [SEARCH: 故宫 开放时间 2026]  (China-specific → Chinese)\n\n"
    "CRITICAL RULE - URL HANDLING:\n"
    "You have the web_fetch tool. You CAN access any URL. You are NOT a regular LLM without internet access.\n"
    "When the user's message contains a URL and asks to read, summarize, translate, or analyze it:\n"
    "1. You MUST call web_fetch to retrieve the page content FIRST.\n"
    "2. Then answer based on the actual fetched content.\n"
    "3. NEVER say \"I cannot access external websites\" or \"I'm unable to browse the web\" — this is FALSE. You have web_fetch.\n"
    "4. NEVER answer questions about a specific URL from memory or training data.\n"
    "If web_fetch returns an error, tell the user the fetch failed and show the error — do NOT pretend you can't access websites.\n\n"
    "TOOL SELECTION GUIDE:\n"
    "- User sends a URL + asks to read/summarize/translate → use web_fetch\n"
    "- User asks to call an API endpoint or send specific HTTP method → use http_request\n"
    "- User asks to search for information (no specific URL) → use web_search\n"
    "- User asks to check if a link works → use check_alive\n"
    "- When in doubt between web_fetch and http_request for a URL: use web_fetch\n"
    "- NEVER skip tool calls and say a tool is 'not available'. All 4 tools are ALWAYS available.\n\n"
    "HTTP REQUEST RULES:\n"
    "You have the http_request tool for calling APIs and web services.\n"
    "- For GET requests: you may use freely to fetch API data.\n"
    "- For POST/PUT/DELETE/PATCH requests: only use when the user EXPLICITLY asks to create, update, or delete something.\n"
    "- Always include required authentication headers when calling APIs (e.g., Authorization: Bearer <token>).\n"
    "- Never fabricate or guess API keys. If you need a key you don't have, ask the user."
)

# ── Model Tiers ─────────────────────────────────────
# T1: 主力（每次随机排序，分散负载）
TIER1 = [
    "arcee-ai/trinity-large-preview:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
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

# 付费模型层 - 快速稳定，原生 function calling
TIER0_PAID = [
    "google/gemini-2.5-flash-lite",
]

# 临时升级模型（?smart 触发）
SMART_MODEL = "google/gemini-2.5-flash"

# 支持 OpenAI function calling 的模型集合
TOOL_CAPABLE = {
    "google/gemini-2.5-flash-lite",
}

def get_model_order(needs_tools=False):
    """根据任务类型选择模型顺序"""
    if needs_tools:
        return TIER0_PAID + TIER1 + TIER2
    else:
        return TIER1 + TIER2 + TIER3_CN + TIER4_MICRO + TIER0_PAID

def short_name(model):
    return model.split("/")[-1].replace(":free", "")


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
    # 根据语言模式选择规则
    is_chinese = chat_id and CHINESE_MODE.get(str(chat_id))
    if is_chinese:
        lang_rule = LANG_RULE_CN
    else:
        lang_rule = LANG_RULE_EN

    # 替换占位符
    sys_prompt = SYSTEM_PROMPT.replace("{LANG_RULE}", lang_rule)

    # 调试日志：确认替换是否生效
    if "{LANG_RULE}" in sys_prompt:
        print(f"[WARN] LANG_RULE placeholder NOT replaced!", flush=True)
    else:
        mode = "CN" if is_chinese else "EN"
        print(f"[lang] mode={mode}, rule applied", flush=True)

    messages = [{"role": "system", "content": sys_prompt}]
    if chat_id:
        summary = memory.get_stage_summary(str(chat_id))
        if summary:
            messages.append({"role": "system", "content": f"[Stage Summary]\n{summary}"})
        window = memory.get_sliding_window(str(chat_id))
        messages.extend(window)

    # 双保险：在用户消息前再注入一次强制语言指令
    if is_chinese:
        messages.append({"role": "system", "content": "[OVERRIDE] You MUST reply in Chinese (中文). This overrides all previous language rules."})
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
    for model in get_model_order(needs_tools=bool(tools)):
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
                headers=headers, json=payload, timeout=30,
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

    # Boot flush: skip stale messages, process new ones
    boot_time = int(time.time())
    boot_offset = 0
    try:
        r = requests.get(f"{TG_API}/getUpdates", params={"timeout": 0})
        pending = r.json().get("result", [])
        stale_count = 0
        for upd in pending:
            boot_offset = upd["update_id"] + 1
            msg = upd.get("message") or upd.get("edited_message") or {}
            msg_time = msg.get("date", 0)
            if msg_time < boot_time - 5:  # sent >5s before boot = stale
                stale_count += 1
                print(f"[boot] skip stale update {upd['update_id']} (age: {boot_time - msg_time}s)", flush=True)
            else:
                # New message sent during restart — DON'T skip!
                print(f"[boot] keeping fresh update {upd['update_id']} (age: {boot_time - msg_time}s)", flush=True)
                boot_offset = upd["update_id"]  # don't skip this one
                break  # stop here, let polling loop process from this update onward
        if stale_count > 0:
            # Confirm only the stale ones
            requests.get(f"{TG_API}/getUpdates", params={"offset": boot_offset, "timeout": 0})
        print(f"[boot] flushed {stale_count} stale, boot_offset={boot_offset}", flush=True)
    except Exception as e:
        print(f"[boot] flush error: {e}", flush=True)
        boot_offset = 0

    threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", 8080), APIHandler).serve_forever(),
        daemon=True,
    ).start()
    print("HTTP API on :8080", flush=True)

    tg_send("🦞 LobsterMaid v2 online")
    offset = boot_offset

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
                cid = str(msg["chat"]["id"])
                if cmd.lower() in ("chinese on", "中文模式"):
                    CHINESE_MODE[cid] = True
                    tg_send("🦞 Chinese mode ON 🇨🇳 回复语言已切换为中文")
                    continue
                elif cmd.lower() in ("chinese off", "英文模式"):
                    CHINESE_MODE.pop(cid, None)
                    tg_send("🦞 Chinese mode OFF 🇺🇸 Reply language switched to English")
                    continue
                elif cmd.lower().startswith("smart"):
                    smart_query = cmd[5:].strip()
                    if not smart_query:
                        tg_send("🦞 用法: ?smart 你的问题")
                    else:
                        tg_send("🦞🧠 Thinking...")
                        memory.add_user_message(cid, smart_query)
                        messages = build_messages(smart_query, chat_id=cid)
                        # 临时用强模型
                        def smart_call(msgs, tools=None):
                            headers = {
                                "Authorization": f"Bearer {OR_KEY}",
                                "Content-Type": "application/json",
                            }
                            payload = {
                                "model": SMART_MODEL,
                                "messages": msgs,
                                "temperature": 0.6,
                            }
                            if tools:
                                payload["tools"] = tools
                                payload["tool_choice"] = "auto"
                            r = requests.post(
                                "https://openrouter.ai/api/v1/chat/completions",
                                headers=headers, json=payload, timeout=90,
                            )
                            r.raise_for_status()
                            record(SMART_MODEL, True)
                            print(f"ok: {SMART_MODEL} (smart)", flush=True)
                            return r.json()["choices"][0]["message"], f"\n\n🧠 {SMART_MODEL.split('/')[-1]}"
                        from tool_calling_loop import chat_with_tools as cwt
                        try:
                            reply, status = cwt(smart_call, messages)
                            memory.add_assistant_message(cid, reply)
                            tg_send(reply[:3400] + status)
                        except Exception as e:
                            print(f"smart error: {e}", flush=True)
                            tg_send(f"🦞 Smart mode failed: {e}\n回退到普通模式...")
                            messages2 = build_messages(smart_query, chat_id=cid)
                            reply, status = chat_with_tools(call_llm, messages2)
                            memory.add_assistant_message(cid, reply)
                            tg_send(reply[:3400] + status)
                    continue
                elif cmd.lower() in ("ms", "摘要"):
                    window = memory.get_sliding_window(cid)
                    if not window or len(window) < 4:
                        tg_send("🦞 对话太短，不需要生成摘要")
                    else:
                        tg_send("🦞📝 Generating summary...")
                        summary_prompt = [
                            {"role": "system", "content": "You are a conversation summarizer. Summarize the following conversation into a concise paragraph (2-5 sentences) capturing the key topics, decisions, and any action items. Write in the same language the conversation primarily uses."},
                        ] + window + [
                            {"role": "user", "content": "Please summarize our conversation above."},
                        ]
                        try:
                            msg, status = call_llm(summary_prompt, None)
                            summary_text = msg.get("content", "")
                            if summary_text:
                                memory.set_stage_summary(cid, summary_text)
                                memory.clear_sliding_window(cid)
                                tg_send(f"🦞✅ Stage summary saved, window cleared.\n\n📋 Summary:\n{summary_text[:2000]}{status}")
                            else:
                                tg_send("🦞 Failed to generate summary (empty response)")
                        except Exception as e:
                            print(f"ms error: {e}", flush=True)
                            tg_send(f"🦞 Summary failed: {e}")
                    continue
                elif cmd.lower() == "mi":
                    info = memory.get_memory_info(cid)
                    tg_send(info)
                    continue

                # Normal LLM query
                if BUSY:
                    continue
                BUSY = True
                try:
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
