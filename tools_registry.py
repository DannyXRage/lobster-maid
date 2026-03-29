"""工具注册表 - 所有工具通过 register_tool() 注册到全局字典"""
TOOLS = {}


def register_tool(name, description, parameters, handler):
    TOOLS[name] = {
        "definition": {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        },
        "handler": handler,
    }


def get_tool_definitions():
    return [t["definition"] for t in TOOLS.values()]


def execute_tool(name, arguments):
    # 工具名别名（Gemini 有时会缩短工具名）
    ALIASES = {"search": "web_search"}
    name = ALIASES.get(name, name)

    if name not in TOOLS:
        return {"error": f"Unknown tool: {name}"}
    try:
        return TOOLS[name]["handler"](**arguments)
    except Exception as e:
        return {"error": str(e)}
