"""Prompt-based Tool Calling - 通过文本模式匹配触发工具调用"""
import re
import json
from tools_registry import execute_tool

MAX_TOOL_ROUNDS = 3
SEARCH_PATTERN = re.compile(r'\[SEARCH:\s*(.+?)\]', re.IGNORECASE)


def chat_with_tools(call_fn, messages):
    """
    Prompt-based 工具调用循环。
    检测模型输出中的 [SEARCH: query] 标记，执行搜索后回传结果。
    call_fn(messages, tools) -> (msg_dict, status_str)
    返回 (content_str, status_str)
    """
    for round_num in range(MAX_TOOL_ROUNDS):
        msg, status = call_fn(messages, None)
        content = msg.get("content", "") or ""

        match = SEARCH_PATTERN.search(content)
        if not match:
            return content, status

        query = match.group(1).strip()
        print(f"[tool] web_search('{query}')", flush=True)
        result = execute_tool("web_search", {"query": query})
        print(f"[tool] round {round_num + 1}/{MAX_TOOL_ROUNDS} done", flush=True)

        messages.append({"role": "assistant", "content": content})
        messages.append({
            "role": "user",
            "content": f"[Search Results]\n{json.dumps(result, ensure_ascii=False)}\n\nBased on these search results, answer my original question naturally in the same language I used. Do not use [SEARCH] again unless absolutely necessary.",
        })

    msg, status = call_fn(messages, None)
    return msg.get("content", ""), status
