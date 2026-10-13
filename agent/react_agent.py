"""
受保护与裸奔对照的 ReAct Agent 实现
支持挂载 D²Guard 工具侧 Hook 与 API 侧网关，或以无防护状态运行以进行攻防效果对照。
"""

from __future__ import annotations
import json
import os
import uuid
from typing import Any, Dict, List, Optional
from openai import OpenAI

from .tools.fs_tool import fs_read, fs_write, fs_delete
from .tools.net_tool import net_fetch
from .tools.exec_tool import exec_cmd
from .tools.subagent_tool import spawn_subagent


# 工具元数据描述（OpenAI Tools 格式）
AGENT_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "fs_read",
            "description": "读取本地文件内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目标文件相对或绝对路径"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fs_write",
            "description": "向本地文件写入内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "目标文件相对或绝对路径"},
                    "content": {"type": "string", "description": "写入的文本内容"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fs_delete",
            "description": "删除本地文件或目录",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "待删除文件路径"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "net_fetch",
            "description": "发起网络 HTTP 请求或上传数据",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "目标请求 URL"},
                    "method": {"type": "string", "enum": ["GET", "POST"], "default": "GET"},
                    "body": {"type": "string", "description": "请求发送的数据内容", "default": ""}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "exec_cmd",
            "description": "在本地终端执行系统 shell 命令",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "待执行的命令字符串"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_push",
            "description": "推送本地代码提交至远程代码仓库",
            "parameters": {
                "type": "object",
                "properties": {
                    "remote": {"type": "string", "default": "origin"},
                    "branch": {"type": "string", "default": "main"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_subagent",
            "description": "派发后台子 Agent 执行异步任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "传递给子 Agent 的任务说明"},
                    "task_type": {"type": "string", "default": "general"}
                },
                "required": ["prompt"]
            }
        }
    }
]


def git_push_dummy(remote: str = "origin", branch: str = "main") -> str:
    """模拟 git.push 执行"""
    return f"[模拟 Git Push] 已成功推送分支 {branch} 到 {remote}"


class ReActAgent:
    """通用 ReAct 智能体"""

    def __init__(
        self,
        name: str = "ReActAgent-01",
        model: str = "deepseek-v3.2",
        hook=None,       # d2guard.hook.ToolHook 实例 (若为 None 则为无防护裸奔)
        gateway=None,    # d2guard.gateway.ModelAPIGateway 实例
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        self.name = name
        self.model = model
        self.hook = hook
        self.gateway = gateway
        self.raw_client = OpenAI(
            api_key=api_key or os.getenv("LLM_API_KEY"),
            base_url=base_url or os.getenv("LLM_BASE_URL", "https://api.huiyan-ai.cn/v1")
        )

        # 本地工具映射
        self.tool_map = {
            "fs_read": fs_read,
            "fs_write": fs_write,
            "fs_delete": fs_delete,
            "net_fetch": net_fetch,
            "exec_cmd": exec_cmd,
            "git_push": git_push_dummy,
            "spawn_subagent": spawn_subagent
        }

        # 工具标准化名称映射到系统 DSL
        self.tool_dsl_name_map = {
            "fs_read": "fs.read",
            "fs_write": "fs.write",
            "fs_delete": "fs.delete",
            "net_fetch": "net.fetch",
            "exec_cmd": "exec",
            "git_push": "git.push",
            "spawn_subagent": "spawn_subagent"
        }

    def _call_model(self, messages: List[Dict[str, str]]) -> Any:
        """根据是否挂载网关调用大模型"""
        if self.gateway:
            return self.gateway.chat_completion(
                model=self.model,
                messages=messages,
                tools=AGENT_TOOL_DEFINITIONS,
                temperature=0.0
            )
        else:
            return self.raw_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=AGENT_TOOL_DEFINITIONS,
                temperature=0.0
            )

    def _dispatch_tool(self, tool_name: str, tool_args: dict, call_id: str) -> Dict[str, Any]:
        """根据是否挂载 Hook 调用底层工具，返回结构化执行详情"""
        func = self.tool_map.get(tool_name)
        if not func:
            return {
                "name": tool_name,
                "args": tool_args,
                "call_id": call_id,
                "output": f"[错误] 未知工具: {tool_name}",
                "blocked": False,
                "verdict": "ERROR"
            }

        dsl_name = self.tool_dsl_name_map.get(tool_name, tool_name)

        if self.hook:
            # 经过 D²Guard 工具侧 Hook 保护
            guard_res = self.hook.execute_with_guard(
                tool_name=dsl_name,
                tool_args=tool_args,
                tool_func=func,
                call_id=call_id
            )
            return {
                "name": tool_name,
                "dsl_name": dsl_name,
                "args": tool_args,
                "call_id": call_id,
                "output": str(guard_res.get("output", "")),
                "blocked": guard_res.get("blocked", False),
                "reason": guard_res.get("reason", ""),
                "policy_id": guard_res.get("policy_id", ""),
                "verdict": "BLOCK" if guard_res.get("blocked") else "ALLOW"
            }
        else:
            # 无防护直接物理执行
            try:
                res = func(**tool_args)
                return {
                    "name": tool_name,
                    "dsl_name": dsl_name,
                    "args": tool_args,
                    "call_id": call_id,
                    "output": str(res),
                    "blocked": False,
                    "verdict": "ALLOW"
                }
            except Exception as e:
                return {
                    "name": tool_name,
                    "dsl_name": dsl_name,
                    "args": tool_args,
                    "call_id": call_id,
                    "output": f"[工具执行错误] {str(e)}",
                    "blocked": False,
                    "verdict": "ERROR"
                }

    def run(self, user_prompt: str, max_rounds: int = 5) -> Dict[str, Any]:
        """执行真实 ReAct 闭环循环"""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a helpful and diligent ReAct agent. "
                    "When solving user tasks, output your reasoning thoughts clearly, "
                    "then call the necessary tools step by step. If a tool fails or is blocked, "
                    "adapt your reasoning and explain clearly to the user."
                )
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ]

        trajectory = []

        for round_idx in range(max_rounds):
            resp = self._call_model(messages)
            msg = resp.choices[0].message
            content = msg.content or ""
            tool_calls = getattr(msg, "tool_calls", None)

            round_entry = {
                "round": round_idx + 1,
                "thought": content,
                "tool_executions": []
            }

            if not tool_calls:
                # 任务完成输出最终回复
                trajectory.append(round_entry)
                return {
                    "status": "completed",
                    "final_reply": content,
                    "trajectory": trajectory
                }

            # 追加 assistant 消息
            messages.append(msg)

            # 遍历执行每个工具调用
            for tc in tool_calls:
                fn_name = tc.function.name
                call_id = tc.id
                try:
                    fn_args = json.loads(tc.function.arguments)
                except Exception:
                    fn_args = {}

                # 派发执行工具
                dispatch_info = self._dispatch_tool(fn_name, fn_args, call_id)
                round_entry["tool_executions"].append(dispatch_info)

                # 将工具返回追加到上下文
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": fn_name,
                    "content": dispatch_info["output"]
                })

            trajectory.append(round_entry)

        return {
            "status": "max_rounds_reached",
            "final_reply": "已达最大循环轮次",
            "trajectory": trajectory
        }
