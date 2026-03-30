"""http_request 工具 - 通用 HTTP 请求"""
import json
import requests as req
from tools_registry import register_tool

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def http_request(method: str, url: str, headers: dict = None, body=None, timeout: int = 30) -> dict:
    """
    发送通用 HTTP 请求到任意 URL。
    
    Args:
        method: HTTP 方法 (GET/POST/PUT/DELETE/PATCH/HEAD)
        url: 请求目标 URL
        headers: 可选字典，自定义请求头
        body: 可选，dict/list 用 json= 发送，其他用 data=
        timeout: 超时秒数，默认 30
    """
    method = method.upper()
    default_headers = {"User-Agent": DEFAULT_UA}
    if headers:
        default_headers.update(headers)
    
    kwargs = {
        "headers": default_headers,
        "timeout": timeout,
        "allow_redirects": True,
    }
    
    # 处理 body
    if body is not None:
        if isinstance(body, (dict, list)):
            kwargs["json"] = body
        else:
            kwargs["data"] = body
    
    try:
        resp = req.request(method, url, **kwargs)
        
        # 尝试解析 JSON
        body_content = ""
        truncated = False
        try:
            json_data = resp.json()
            body_content = json.dumps(json_data, ensure_ascii=False, indent=2)
        except (ValueError, TypeError):
            body_content = resp.text
        
        # 截断到 4000 字符
        if len(body_content) > 4000:
            body_content = body_content[:4000] + "\n[...truncated]"
            truncated = True
        
        return {
            "status_code": resp.status_code,
            "content_type": resp.headers.get("Content-Type", ""),
            "final_url": resp.url,
            "body": body_content,
            "truncated": truncated,
        }
    except req.RequestException as e:
        return {"status_code": "error", "error": str(e)}


register_tool(
    name="http_request",
    description="Send an HTTP request to any URL. Input: {method: string (GET/POST/PUT/DELETE/PATCH/HEAD), url: string, headers?: object, body?: object|string, timeout?: number}. Returns status code, response headers, and body.",
    parameters={
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "description": "HTTP method: GET, POST, PUT, DELETE, PATCH, or HEAD",
                "default": "GET",
            },
            "url": {"type": "string", "description": "The URL to request"},
            "headers": {"type": "object", "description": "Optional custom headers (e.g., Authorization)"},
            "body": {"type": ["object", "string"], "description": "Request body (dict/list for JSON, string for raw)"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
        },
        "required": ["method", "url"],
    },
    handler=http_request,
)
