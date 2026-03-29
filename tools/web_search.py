"""web_search 工具 - 网络搜索（DuckDuckGo）"""
from ddgs import DDGS
from tools_registry import register_tool


def search_web(query: str, max_results: int = 5, region: str = "wt-wt") -> dict:
    """执行网络搜索，返回结果摘要"""
    try:
        d = DDGS()
        results = list(d.text(
            query,
            region=region,
            max_results=max_results,
        ))

        if not results:
            return {"results": [], "message": "未找到相关结果"}

        formatted = []
        for r in results:
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            })

        return {"results": formatted, "query": query}

    except Exception as e:
        return {"error": f"搜索失败: {str(e)}", "query": query}


register_tool(
    name="web_search",
    description="Search the web for current information. Use this when you need to find up-to-date facts, news, weather, prices, or any real-time public information. Do NOT use this for general knowledge questions that don't require current data.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query string",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5)",
                "default": 5,
            },
            "region": {
                "type": "string",
                "description": "Search region: 'wt-wt' for global, 'cn-zh' for China, 'us-en' for US",
                "default": "wt-wt",
            },
        },
        "required": ["query"],
    },
    handler=search_web,
)
