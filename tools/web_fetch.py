"""web_fetch 工具 - 网页抓取和存活检测"""
import requests as req
from bs4 import BeautifulSoup
from tools_registry import register_tool

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _get_meta(soup, attr: str, value: str) -> str:
    """安全提取 meta 标签 content"""
    tag = soup.find("meta", attrs={attr: value})
    return tag.get("content", "") if tag else ""


def _extract_text(soup: BeautifulSoup) -> str:
    """移除无用标签后提取纯文本"""
    # 复制 soup 避免修改原对象
    soup_copy = BeautifulSoup(str(soup), "lxml")
    # 移除脚本、样式、导航、头部、底部等无用标签
    for tag in soup_copy(["script", "style", "nav", "header", "footer", "noscript", "iframe"]):
        tag.decompose()
    return soup_copy.get_text(separator="\n", strip=True)


def fetch_page(url: str) -> dict:
    """抓取网页完整内容：标题、描述、正文等"""
    try:
        resp = req.get(url, headers={"User-Agent": DEFAULT_UA}, timeout=10, allow_redirects=True)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "lxml")
        
        # 提取基本信息
        title = soup.title.string if soup.title else ""
        meta_desc = _get_meta(soup, "name", "description")
        og_title = _get_meta(soup, "property", "og:title")
        og_desc = _get_meta(soup, "property", "og:description")
        og_image = _get_meta(soup, "property", "og:image")
        
        # 提取正文
        main_content = _extract_text(soup)
        # 截断到 4000 字符
        if len(main_content) > 4000:
            main_content = main_content[:4000] + "\n[...truncated]"
        
        return {
            "status_code": resp.status_code,
            "final_url": resp.url,
            "title": title,
            "meta_description": meta_desc,
            "og_title": og_title,
            "og_description": og_desc,
            "og_image": og_image,
            "content": main_content,
        }
    except req.RequestException as e:
        return {"status": "error", "error": str(e)}


def check_alive(url: str) -> dict:
    """检测 URL 是否可访问（HEAD 请求，更快）"""
    try:
        resp = req.head(url, headers={"User-Agent": DEFAULT_UA}, timeout=10, allow_redirects=True)
        return {
            "alive": True,
            "status_code": resp.status_code,
            "final_url": resp.url,
        }
    except req.RequestException as e:
        return {"alive": False, "error": str(e)}


# 注册工具
register_tool(
    name="web_fetch",
    description="Fetch and read a webpage's full content. Input: {url: string}. Returns page title, description, and main text content.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to fetch"},
        },
        "required": ["url"],
    },
    handler=fetch_page,
)

register_tool(
    name="check_alive",
    description="Check if a URL is accessible. Input: {url: string}. Returns alive status and HTTP status code.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to check"},
        },
        "required": ["url"],
    },
    handler=check_alive,
)
