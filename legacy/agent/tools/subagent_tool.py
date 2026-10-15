"""
子 Agent 派发工具 (subagent)
"""

from typing import Dict, Any


def spawn_subagent(prompt: str, task_type: str = "general") -> str:
    """派发后台子 Agent 执行特定任务"""
    return f"[子 Agent 已启动] 任务类型: {task_type}, 提示词长度: {len(prompt)}"
