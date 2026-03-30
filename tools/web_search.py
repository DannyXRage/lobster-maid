"""web_search 工具 - SearXNG 聚合搜索 + DuckDuckGo fallback"""
import json
import requests as req
from ddgs import DDGS
from tools_registry import register_tool

SEARXNG_URL = "http://searxng:8080/search"


def _search_searxng(query, max_results=5):
    """SearXNG 聚合搜索（主引擎：Google + Bing + DuckDuckGo + Wikipedia + GitHub）"""
    try:
        resp = req.get(SEARXNG_URL, params={
            "q": query,
            "format": "json",
            "categories": "general",
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])[:max_results]
        formatted = []
        for item in results:
            formatted.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "engines": ", ".join(item.get("engines", [])),
            })
        return formatted
    except Exception as e:
        print(f"[searxng] error: {e}", flush=True)
        return None


def _search_ddg(query, max_results=5, region="wt-wt"):
    """DuckDuckGo fallback 搜索"""
    try:
        d = DDGS()
        results = list(d.text(query, region=region, max_results=max_results))
        formatted = []
        for item in results:
            formatted.append({
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "snippet": item.get("body", ""),
                "engines": "duckduckgo",
            })
        return formatted
    except Exception as e:
        print(f"[ddg-fallback] error: {e}", flush=True)
        return None


def search_web(query: str, max_results: int = 5, region: str = "wt-wt") -> dict:
    """执行网络搜索：优先 SearXNG 聚合引擎，失败回退 DuckDuckGo"""
    # 主搜索：SearXNG（聚合 Google + Bing + DDG + Wikipedia + GitHub）
    results = _search_searxng(query, max_results)
    source = "searxng"

    # Fallback：DuckDuckGo 直连
    if results is None:
        print("[search] SearXNG failed, falling back to DuckDuckGo", flush=True)
        results = _search_ddg(query, max_results, region)
        source = "duckduckgo-fallback"

    if not results:
        return {"results": [], "message": "未找到相关结果", "source": source}

    return {"results": results, "query": query, "source": source}


register_tool(
    name="web_search",
    description="Search the web for current information. Uses SearXNG (Google+Bing+DuckDuckGo aggregation) with DuckDuckGo as fallback.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query string"},
            "max_results": {"type": "integer", "description": "Max results (default 5)", "default": 5},
            "region": {"type": "string", "description": "Search region: 'wt-wt' for global, 'cn-zh' for China", "default": "wt-wt"},
        },
        "required": ["query"],
    },
    handler=search_web,
)
