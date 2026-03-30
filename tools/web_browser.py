"""web_browser 工具 - Playwright 浏览器渲染、截图和PDF"""
import os
import time
from tools_registry import register_tool

# 文件保存目录
TEMP_DIR = "/tmp/lobster_files"
os.makedirs(TEMP_DIR, exist_ok=True)

# 懒加载：浏览器在首次调用时启动，不在 import 时启动
_playwright = None
_browser = None

# 共用 User-Agent
DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


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
    context = browser.new_context(user_agent=DEFAULT_UA)
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


def screenshot(url: str, timeout: int = 20000) -> dict:
    """
    使用 Playwright 对网页进行全页截图。

    Args:
        url: 要截图的 URL
        timeout: 等待超时时间（毫秒），默认 20000ms

    Returns:
        包含 success、file_path、file_type、url 的字典，异常时返回 {"success": False, "error": str}
    """
    browser = get_browser()
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent=DEFAULT_UA,
    )
    page = context.new_page()
    try:
        page.goto(url, wait_until="networkidle", timeout=timeout)
        filename = f"screenshot_{int(time.time())}_{hash(url) % 10000}.png"
        filepath = os.path.join(TEMP_DIR, filename)
        # 限制截图高度，防止 TG sendPhoto 拒绝（宽+高总和 < 10000px）
        body_height = page.evaluate("document.body.scrollHeight")
        use_full_page = body_height <= 8000  # TG 友好上限
        page.screenshot(path=filepath, full_page=use_full_page)
        return {
            "success": True,
            "file_path": filepath,
            "file_type": "photo",
            "url": url,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        context.close()


def to_pdf(url: str, timeout: int = 20000) -> dict:
    """
    使用 Playwright 将网页保存为 PDF 文档。

    Args:
        url: 要保存为 PDF 的 URL
        timeout: 等待超时时间（毫秒），默认 20000ms

    Returns:
        包含 success、file_path、file_type、url 的字典，异常时返回 {"success": False, "error": str}
    """
    browser = get_browser()
    context = browser.new_context(user_agent=DEFAULT_UA)
    page = context.new_page()
    try:
        page.goto(url, wait_until="networkidle", timeout=timeout)
        filename = f"page_{int(time.time())}_{hash(url) % 10000}.pdf"
        filepath = os.path.join(TEMP_DIR, filename)
        page.pdf(path=filepath, format="A4", print_background=True)
        return {
            "success": True,
            "file_path": filepath,
            "file_type": "document",
            "url": url,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        context.close()


# ── 工具注册 ──────────────────────────────────────────

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

register_tool(
    name="screenshot",
    description="Take a full-page screenshot of a webpage using a real browser. Returns the screenshot as a PNG image sent directly to the chat. Input: {url: string}. Use for: visual preview, webpage archival, monitoring changes.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to screenshot"},
        },
        "required": ["url"],
    },
    handler=screenshot,
)

register_tool(
    name="to_pdf",
    description="Save a webpage as a PDF document with full layout using a real browser. Returns the PDF file sent directly to the chat. Input: {url: string}. Use for: archiving important pages, preventing 404 loss, offline reading.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to save as PDF"},
        },
        "required": ["url"],
    },
    handler=to_pdf,
)
