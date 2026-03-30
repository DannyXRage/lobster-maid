"""Hybrid Tool Calling - 方案A(function calling) + 方案B(prompt-based) 混合"""
import re
import json
from tools_registry import get_tool_definitions, execute_tool

MAX_TOOL_ROUNDS = 3
SEARCH_PATTERN = re.compile(r'\[SEARCH:\s*(.+?)\]', re.IGNORECASE)


def chat_with_tools(call_fn, messages):
    """
    混合工具调用循环。
    - 付费模型走方案A：OpenAI function calling（tool_calls 字段）
    - 免费模型走方案B：prompt-based（[SEARCH: query] 正则匹配）
    call_fn(messages, tools) -> (msg_dict, status_str)
    返回 (content_str, status_str, pending_files)
        pending_files: [{"file_path": str, "file_type": str}, ...]
    """
    tools = get_tool_definitions()
    pending_files = []

    for round_num in range(MAX_TOOL_ROUNDS):
        msg, status = call_fn(messages, tools if tools else None)
        content = msg.get("content", "") or ""

        # 方案A：检查 tool_calls（付费模型）
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            messages.append(msg)
            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    args = {}
                if fn_name == "login_session":
                    print(f"[tool-A] login_session(url={args.get('url','?')}, save_as={args.get('save_as','?')}, steps=[redacted])", flush=True)
                else:
                    print(f"[tool-A] {fn_name}({args})", flush=True)
                result = execute_tool(fn_name, args)
                
                # 检查是否有文件返回
                if isinstance(result, dict) and result.get("file_path"):
                    pending_files.append({
                        "file_path": result["file_path"],
                        "file_type": result.get("file_type", "document"),
                    })
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                })
            print(f"[tool-A] round {round_num + 1}/{MAX_TOOL_ROUNDS} done", flush=True)
            continue

        # 方案B：检查 [SEARCH: query]（免费模型）
        match = SEARCH_PATTERN.search(content)
        if match:
            query = match.group(1).strip()
            print(f"[tool-B] web_search('{query}')", flush=True)
            result = execute_tool("web_search", {"query": query})
            print(f"[tool-B] round {round_num + 1}/{MAX_TOOL_ROUNDS} done", flush=True)
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": f"[Search Results]\n{json.dumps(result, ensure_ascii=False)}\n\nBased on these search results, answer my original question naturally in the same language I used. Include source URLs from the results so the user can verify the information. Do not use [SEARCH] again unless absolutely necessary.",
            })
            continue

        # 无工具调用，直接返回
        return content, status, pending_files

    # 超过最大轮数
    msg, status = call_fn(messages, None)
    return msg.get("content", ""), status, pending_files
