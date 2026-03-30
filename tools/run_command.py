"""run_command 工具 - 在 VPS 上执行白名单系统命令"""
import os
import re
import subprocess
from tools_registry import register_tool

# ========== 安全配置 ==========

# 允许的路径前缀（用于文件浏览命令路径校验）
ALLOWED_PATHS = [
    "/app/",
    "/home/young/lobster/",
    "/proc/cpuinfo",
    "/proc/meminfo",
    "/etc/hostname",
    "/etc/os-release",
]

# 命令白名单配置
ALLOWED_COMMANDS = {
    # 系统信息（精确或前缀匹配）
    "exact": [
        "free", "df", "uptime", "uname", "whoami", "hostname", "date", "pwd",
    ],
    "prefix": [
        "free ", "df ", "uptime", "uname ", "whoami", "hostname", "date ", "pwd",
    ],
    
    # Docker（精确子命令）
    "docker": [
        "docker ps",
        "docker logs",
        "docker images",
        "docker stats",
        "docker compose up",
        "docker compose down",
        "docker compose restart",
        "docker compose build",
        "docker compose pull",
        "docker compose logs",
        "docker compose ps",
        "docker compose config",
    ],
    
    # Git
    "git": [
        "git status",
        "git log",
        "git pull",
        "git diff",
        "git branch",
    ],
    
    # 网络
    "network": [
        "ping -c",
        "ss",
        "ip addr",
    ],
    
    # 服务（仅限 cloudflared）
    "service": [
        "systemctl status cloudflared",
        "systemctl restart cloudflared",
    ],
    
    # 进程
    "process": [
        "ps aux",
        "ps -ef",
        "top -bn1",
    ],
    
    # 文件浏览（需要路径校验）
    "file_browse": [
        "ls",
        "cat",
        "head",
        "tail",
        "wc",
        "du",
        "find",
    ],
}

# 黑名单关键词（包含任意一个即拒绝）
BLACKLIST_KEYWORDS = [
    "rm", "rmdir", "chmod", "chown",
    "apt", "apt-get", "pip install",
    "reboot", "shutdown", "poweroff",
    "ssh", "scp",
    "wget", "curl",
    "docker run", "docker exec", "docker compose exec", "docker compose run",
    "eval",
    "> /", ">> /",
    "| sh", "| bash", "| zsh",
    "$(",
]

# ========== 安全检查函数 ==========

def check_blacklist(command: str) -> tuple:
    """检查命令是否包含黑名单关键词"""
    cmd_lower = command.lower()
    for keyword in BLACKLIST_KEYWORDS:
        if keyword in cmd_lower:
            return True, f"Blacklisted keyword: {keyword}"
    return False, ""


def check_whitelist(command: str) -> tuple:
    """检查命令是否在白名单中"""
    cmd = " ".join(command.split())
    cmd_lower = cmd.lower()
    
    # 检查精确匹配列表
    for exact_cmd in ALLOWED_COMMANDS["exact"]:
        if cmd == exact_cmd or cmd_lower == exact_cmd:
            return True, ""
    
    # 检查前缀匹配
    for prefix in ALLOWED_COMMANDS["prefix"]:
        if cmd.startswith(prefix) or cmd_lower.startswith(prefix.lower()):
            return True, ""
    
    # 检查 Docker 命令
    for docker_cmd in ALLOWED_COMMANDS["docker"]:
        if cmd.startswith(docker_cmd) or cmd_lower.startswith(docker_cmd.lower()):
            return True, ""
    
    # 检查 Git 命令
    for git_cmd in ALLOWED_COMMANDS["git"]:
        if cmd.startswith(git_cmd) or cmd_lower.startswith(git_cmd.lower()):
            return True, ""
    
    # 检查网络命令
    for net_cmd in ALLOWED_COMMANDS["network"]:
        if cmd.startswith(net_cmd) or cmd_lower.startswith(net_cmd.lower()):
            if net_cmd == "ping -c" and not re.search(r'ping\s+-[a-zA-Z]*c\d*', cmd):
                return False, "ping requires -c parameter"
            return True, ""
    
    # 检查服务命令
    for svc_cmd in ALLOWED_COMMANDS["service"]:
        if cmd.startswith(svc_cmd) or cmd_lower.startswith(svc_cmd.lower()):
            return True, ""
    
    # 检查进程命令
    for proc_cmd in ALLOWED_COMMANDS["process"]:
        if cmd.startswith(proc_cmd) or cmd_lower.startswith(proc_cmd.lower()):
            return True, ""
    
    # 检查文件浏览命令（需要路径校验）
    for fb_cmd in ALLOWED_COMMANDS["file_browse"]:
        if cmd.startswith(fb_cmd) or cmd_lower.startswith(fb_cmd.lower()):
            if not validate_file_path(cmd, fb_cmd):
                return False, f"Path not allowed for {fb_cmd} command"
            return True, ""
    
    return False, "Command not in whitelist"


def validate_file_path(command: str, base_cmd: str) -> bool:
    """验证文件浏览命令的路径是否在允许范围内"""
    parts = command.split()
    if len(parts) < 2:
        return True
    
    path_args = parts[1:]
    paths = [arg for arg in path_args if not arg.startswith("-")]
    
    if not paths:
        return True
    
    for path in paths:
        try:
            abs_path = os.path.abspath(path)
            # 检查路径是否在允许范围内（支持带或不带尾斜杠）
            allowed = False
            for allowed_prefix in ALLOWED_PATHS:
                if abs_path == allowed_prefix.rstrip('/') or abs_path.startswith(allowed_prefix):
                    allowed = True
                    break
            if not allowed:
                return False
        except Exception:
            return False
    
    return True


def validate_timeout(timeout: int) -> int:
    """验证并规范化 timeout 值"""
    if timeout < 5:
        timeout = 5
    elif timeout > 120:
        timeout = 120
    return timeout


# ========== 核心功能函数 ==========

def run_command(command: str, timeout: int = 30) -> dict:
    """
    执行白名单系统命令
    """
    import datetime
    
    timestamp = datetime.datetime.now().isoformat()
    print(f"[run_command] [{timestamp}] EXECUTING: {command}", flush=True)
    
    timeout = validate_timeout(timeout)
    
    # 黑名单检查
    blocked, reason = check_blacklist(command)
    if blocked:
        error_msg = f"Security check failed: {reason}"
        print(f"[run_command] [{timestamp}] BLOCKED: {error_msg}", flush=True)
        return {"success": False, "error": error_msg}
    
    # 白名单检查
    allowed, reason = check_whitelist(command)
    if not allowed:
        error_msg = f"Security check failed: {reason}"
        print(f"[run_command] [{timestamp}] BLOCKED: {error_msg}", flush=True)
        return {"success": False, "error": error_msg}
    
    # 确定工作目录（/app 在 Docker 中存在，本地测试可能不存在）
    cwd = "/app" if os.path.exists("/app") else os.getcwd()
    
    # 执行命令
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        
        # 截断输出
        stdout = result.stdout
        stderr = result.stderr
        truncated = False
        
        if len(stdout) > 4000:
            stdout = stdout[:4000] + "\n... [truncated]"
            truncated = True
        
        if len(stderr) > 2000:
            stderr = stderr[:2000] + "\n... [truncated]"
            truncated = True
        
        print(f"[run_command] [{timestamp}] COMPLETED: rc={result.returncode}", flush=True)
        
        return {
            "success": True,
            "stdout": stdout,
            "stderr": stderr,
            "return_code": result.returncode,
            "truncated": truncated,
        }
        
    except subprocess.TimeoutExpired:
        error_msg = f"Command timed out after {timeout} seconds"
        print(f"[run_command] [{timestamp}] TIMEOUT: {error_msg}", flush=True)
        return {"success": False, "error": error_msg}
        
    except Exception as e:
        error_msg = f"Execution error: {str(e)}"
        print(f"[run_command] [{timestamp}] ERROR: {error_msg}", flush=True)
        return {"success": False, "error": error_msg}


def list_allowed_commands() -> dict:
    """
    列出所有允许的命令类别和前缀
    """
    return {
        "categories": {
            "system_info": {
                "description": "System information commands",
                "commands": [
                    "free", "df", "uptime", "uname", "whoami", "hostname", "date", "pwd"
                ]
            },
            "docker": {
                "description": "Docker management (read-only and compose operations)",
                "commands": [
                    "docker ps",
                    "docker logs",
                    "docker images",
                    "docker stats",
                    "docker compose up",
                    "docker compose down",
                    "docker compose restart",
                    "docker compose build",
                    "docker compose pull",
                    "docker compose logs",
                    "docker compose ps",
                    "docker compose config"
                ]
            },
            "git": {
                "description": "Git repository operations",
                "commands": [
                    "git status",
                    "git log",
                    "git pull",
                    "git diff",
                    "git branch"
                ]
            },
            "network": {
                "description": "Network diagnostic commands",
                "commands": [
                    "ping -c <count> <host>  (count required)",
                    "ss",
                    "ip addr"
                ]
            },
            "services": {
                "description": "Systemd service management (cloudflared only)",
                "commands": [
                    "systemctl status cloudflared",
                    "systemctl restart cloudflared"
                ]
            },
            "process": {
                "description": "Process inspection commands",
                "commands": [
                    "ps aux",
                    "ps -ef",
                    "top -bn1"
                ]
            },
            "file_browse": {
                "description": "File browsing commands (path restricted)",
                "allowed_paths": ALLOWED_PATHS,
                "commands": [
                    "ls <path>",
                    "cat <path>",
                    "head <path>",
                    "tail <path>",
                    "wc <path>",
                    "du <path>",
                    "find <path>"
                ]
            }
        },
        "note": "File browsing commands only allow access to specific paths. Blacklisted keywords will cause rejection."
    }


# ========== 工具注册 ==========

register_tool(
    name="run_command",
    description="Execute a whitelisted system command on the VPS. Only commands matching the security whitelist are allowed. Use list_allowed_commands to check available commands first.",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The system command to execute (must be in whitelist)"
            },
            "timeout": {
                "type": "integer",
                "description": "Command timeout in seconds (5-120, default 30)",
                "default": 30
            }
        },
        "required": ["command"],
    },
    handler=run_command,
)


register_tool(
    name="list_allowed_commands",
    description="List all allowed command categories and their prefixes for run_command",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    handler=list_allowed_commands,
)
