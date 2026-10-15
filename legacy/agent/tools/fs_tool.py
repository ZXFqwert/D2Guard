"""
受控文件系统工具 (fs)
"""

import os
from typing import Dict, Any


def fs_read(path: str) -> str:
    """读取指定路径文件内容"""
    if not os.path.exists(path):
        return f"[错误] 文件不存在: {path}"
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        return f"[错误] 读取文件失败: {str(e)}"


def fs_write(path: str, content: str) -> str:
    """向指定路径写入文件内容"""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"[成功] 写入文件完成: {path} ({len(content)} 字节)"
    except Exception as e:
        return f"[错误] 写入文件失败: {str(e)}"


def fs_delete(path: str) -> str:
    """删除指定路径文件"""
    if not os.path.exists(path):
        return f"[错误] 文件不存在: {path}"
    try:
        if os.path.isdir(path):
            import shutil
            shutil.rmtree(path)
        else:
            os.remove(path)
        return f"[成功] 已删除: {path}"
    except Exception as e:
        return f"[错误] 删除失败: {str(e)}"
