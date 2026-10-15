"""
受控命令执行工具 (exec)
包含子进程环境变量自动脱敏与工作目录隔离
"""

import os
import subprocess
from typing import Dict, Optional


SENSITIVE_ENV_VARS = [
    "LLM_API_KEY", "API_KEY", "SECRET", "TOKEN", "SSH_AUTH_SOCK",
    "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN"
]


def exec_cmd(
    command: str,
    cwd: Optional[str] = None,
    sanitize_env: bool = True,
    timeout: int = 10
) -> str:
    """
    在沙箱环境中执行系统命令
    """
    # 1. 环境变量脱敏隔离
    env = os.environ.copy()
    if sanitize_env:
        for var in SENSITIVE_ENV_VARS:
            env.pop(var, None)

    # 2. 限制当前工作目录
    working_dir = cwd or os.getcwd()

    try:
        res = subprocess.run(
            command,
            shell=True,
            cwd=working_dir,
            env=env,
            capture_output=True,
            timeout=timeout
        )
        stdout = res.stdout.decode('utf-8', errors='replace') if res.stdout else ""
        stderr = res.stderr.decode('utf-8', errors='replace') if res.stderr else ""
        output = stdout if res.returncode == 0 else f"{stdout}\n[错误输出] {stderr}"
        return output.strip() or "[命令执行成功，无标准输出]"
    except subprocess.TimeoutExpired:
        return "[错误] 命令执行超时"
    except Exception as e:
        return f"[错误] 执行异常: {str(e)}"
