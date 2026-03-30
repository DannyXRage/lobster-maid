"""web_browser 工具 - Playwright 浏览器渲染、截图和PDF"""
import os
import time
from tools_registry import register_tool

# 文件保存目录
TEMP_DIR = "/tmp/lobster_files"
os.makedirs(TEMP_DIR, exist_ok=True)

# Auth session 目录
AUTH_DIR = "/app/auth"
os.makedirs(AUTH_DIR, exist_ok=True)

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


def get_browser_context(auth_name=None):
    """创建浏览器上下文，可选加载已保存的 session"""
    browser = get_browser()
    opts = {
        "viewport": {"width": 1280, "height": 720},
        "user_agent": DEFAULT_UA
    }
    if auth_name:
        auth_path = os.path.join(AUTH_DIR, f"{auth_name}_auth.json")
        if os.path.exists(auth_path):
            opts["storage_state"] = auth_path
            print(f"[browser] loaded session: {auth_name}", flush=True)
    return browser.new_context(**opts)


def render_spa(url: str, timeout: int = 15000, auth=None) -> dict:
    """
    使用 Playwright 渲染 JavaScript-heavy 网页并提取文本内容。

    Args:
        url: 要渲染的 URL
        timeout: 等待超时时间（毫秒），默认 15000ms
        auth: 可选的已保存 session 名称，用于访问需要登录的页面

    Returns:
        包含 title、text、url、truncated 的字典，异常时返回 {"error": str}
    """
    context = get_browser_context(auth)
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


def screenshot(url: str, timeout: int = 20000, auth=None) -> dict:
    """
    使用 Playwright 对网页进行全页截图。

    Args:
        url: 要截图的 URL
        timeout: 等待超时时间（毫秒），默认 20000ms
        auth: 可选的已保存 session 名称，用于访问需要登录的页面

    Returns:
        包含 success、file_path、file_type、url 的字典，异常时返回 {"success": False, "error": str}
    """
    context = get_browser_context(auth)
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


def to_pdf(url: str, timeout: int = 20000, auth=None) -> dict:
    """
    使用 Playwright 将网页保存为 PDF 文档。

    Args:
        url: 要保存为 PDF 的 URL
        timeout: 等待超时时间（毫秒），默认 20000ms
        auth: 可选的已保存 session 名称，用于访问需要登录的页面

    Returns:
        包含 success、file_path、file_type、url 的字典，异常时返回 {"success": False, "error": str}
    """
    context = get_browser_context(auth)
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


def login_session(url: str, steps: list, save_as: str, timeout: int = 30000) -> dict:
    """
    自动化登录网站并保存浏览器 session。

    Args:
        url: 登录页面 URL
        steps: 登录步骤数组，每个步骤包含 action 和相关参数
               支持的动作:
               - fill(selector, value): 使用 fill 填充输入框
               - click(selector): 点击元素并等待 networkidle
               - type(selector, value): 逐字符输入（用于某些 JS 输入框）
               - wait(ms): 等待指定毫秒
               - wait_url(pattern): 等待 URL 匹配指定模式
        save_as: session 名称，保存为 <name>_auth.json
        timeout: 等待超时时间（毫秒），默认 30000ms

    Returns:
        包含 success、auth_file、message 的字典，失败时返回 {"success": False, "error": str}
    """
    browser = get_browser()
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent=DEFAULT_UA
    )
    page = context.new_page()
    try:
        page.goto(url, wait_until="networkidle", timeout=timeout)

        # 执行登录步骤
        for step in steps:
            action = step["action"]
            if action == "fill":
                page.fill(step["selector"], step["value"])
                page.wait_for_timeout(300)  # 确保值写入 DOM
            elif action == "click":
                # 如果下一步是 wait_url，不在这里等 navigation（让 wait_url 处理）
                step_idx = steps.index(step)
                next_is_wait_url = (step_idx + 1 < len(steps) and steps[step_idx + 1].get("action") == "wait_url")
                if next_is_wait_url:
                    page.click(step["selector"])
                    # 给页面一点时间开始 navigation
                    page.wait_for_timeout(1000)
                else:
                    try:
                        with page.expect_navigation(timeout=timeout):
                            page.click(step["selector"])
                    except Exception:
                        # 有些 click 不触发 navigation（如展开菜单），忽略
                        pass
            elif action == "wait":
                page.wait_for_timeout(int(step.get("ms", 2000)))
            elif action == "wait_url":
                pattern = step["pattern"]
                # 如果 pattern 不含通配符 *，自动包裹为 glob "contains" 匹配
                if "*" not in pattern:
                    pattern = f"**{pattern}**"
                page.wait_for_url(pattern, timeout=timeout)
            elif action == "type":
                # 逐字符输入（用于某些 JS 输入框）
                page.type(step["selector"], step["value"], delay=50)

        # 保存登录态
        auth_path = os.path.join(AUTH_DIR, f"{save_as}_auth.json")
        context.storage_state(path=auth_path)
        return {
            "success": True,
            "auth_file": save_as,
            "message": f"Session saved as {save_as}_auth.json"
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        context.close()


def list_sessions() -> dict:
    """
    列出所有已保存的浏览器登录 session。

    Returns:
        包含 sessions 列表和 count 的字典
    """
    try:
        files = [f.replace("_auth.json", "") for f in os.listdir(AUTH_DIR) if f.endswith("_auth.json")]
        return {"sessions": files, "count": len(files)}
    except Exception as e:
        return {"sessions": [], "count": 0, "error": str(e)}


# ── 工具注册 ──────────────────────────────────────────

register_tool(
    name="render_spa",
    description="Render a JavaScript-heavy webpage using a real browser and extract its text content. Use this ONLY when web_fetch returns empty or incomplete content (e.g., React/Vue/Angular SPA sites). Input: {url: string}. Returns page title and full rendered text content.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to render"},
            "auth": {"type": "string", "description": "Optional saved session name to use for authenticated access (e.g. 'github', 'nas')"},
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
            "auth": {"type": "string", "description": "Optional saved session name to use for authenticated access (e.g. 'github', 'nas')"},
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
            "auth": {"type": "string", "description": "Optional saved session name to use for authenticated access (e.g. 'github', 'nas')"},
        },
        "required": ["url"],
    },
    handler=to_pdf,
)

register_tool(
    name="login_session",
    description="Automate login on a website and save the browser session for future use. After saving, other browser tools (render_spa, screenshot, to_pdf) can use the session via the 'auth' parameter. Input: {url: login page URL, steps: array of actions, save_as: session name}. Actions: fill(selector, value), click(selector), type(selector, value), wait(ms), wait_url(pattern).",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The login page URL"},
            "steps": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Login steps: [{action, selector?, value?, pattern?, ms?}]"
            },
            "save_as": {"type": "string", "description": "Session name (e.g. 'github', 'nas'). Saved as <name>_auth.json"},
        },
        "required": ["url", "steps", "save_as"],
    },
    handler=login_session,
)

register_tool(
    name="list_sessions",
    description="List all saved browser login sessions. Returns session names that can be passed as 'auth' parameter to render_spa, screenshot, or to_pdf.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    },
    handler=list_sessions,
)
