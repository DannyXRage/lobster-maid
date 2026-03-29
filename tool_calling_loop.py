"""Tool Calling 调度循环 - 处理多轮工具调用"""
import json
from tools_registry import get_tool_definitions, execute_tool

MAX_TOOL_ROUNDS = 5


def chat_with_tools(call_fn, messages):
    """
    带工具调用的多轮对话。
    call_fn(messages, tools) -> (msg_dict, status_str)
    返回 (content_str, status_str)
    """
    tools = get_tool_definitions()

    for round_num in range(MAX_TOOL_ROUNDS):
        msg, status = call_fn(messages, tools if tools else None)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return msg.get("content", ""), status

        messages.append(msg)

        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, KeyError):
                args = {}

            print(f"[tool] {fn_name}({args})", flush=True)
            result = execute_tool(fn_name, args)

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False),
            })

        print(f"[tool] round {round_num + 1}/{MAX_TOOL_ROUNDS} done", flush=True)

    print("[tool] max rounds reached, final call without tools", flush=True)
    msg, status = call_fn(messages, None)
    return msg.get("content", ""), status
