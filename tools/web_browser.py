"""web_browser 工具 - Playwright 浏览器渲染"""
from tools_registry import register_tool

# 懒加载：浏览器在首次调用时启动，不在 import 时启动
_playwright = None
_browser = None


def get_browser():
    """获取或启动 Chromium 浏览器实例（懒加载）"""
    global _playwright, _browser
    if _browser is None:
        from playwright.sync_api import sync_playwright
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
    return _browser


def render_spa(url: str, timeout: int = 15000) -> dict:
    """
    使用 Playwright 渲染 JavaScript-heavy 网页并提取文本内容。

    Args:
        url: 要渲染的 URL
        timeout: 等待超时时间（毫秒），默认 15000ms

    Returns:
        包含 title、text、url、truncated 的字典，异常时返回 {"error": str}
    """
    browser = get_browser()
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    page = context.new_page()
    try:
        page.goto(url, wait_until="networkidle", timeout=timeout)
        title = page.title()
        text = page.inner_text("body")
        final_url = page.url

        # 截断到 4000 字符
        truncated = len(text) > 4000
        if truncated:
            text = text[:4000] + "\n[...truncated]"

        return {
            "title": title,
            "text": text,
            "url": final_url,
            "truncated": truncated,
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        context.close()


# 注册工具
register_tool(
    name="render_spa",
    description="Render a JavaScript-heavy webpage using a real browser and extract its text content. Use this ONLY when web_fetch returns empty or incomplete content (e.g., React/Vue/Angular SPA sites). Input: {url: string}. Returns page title and full rendered text content.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to render"},
        },
        "required": ["url"],
    },
    handler=render_spa,
)
