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


from d2guard.llm_config import create_llm_client
import copy
import time

class ReActAgent:
    """A real model/tool loop, with resumable batched tool calls and observable events."""
    def __init__(self, name="ReActAgent-01", model=None, hook=None, gateway=None,
                 api_key=None, base_url=None, client=None, tool_map=None,
                 tool_definitions=None, event_callback=None, provider=None, max_tool_calls=16, max_wall_seconds=150,
                 agent_framework="d2_react"):
        self.name, self.hook, self.gateway = name, hook, gateway
        self.agent_framework = agent_framework
        configured, configured_model = create_llm_client(provider=provider, api_key=api_key,
                                                        base_url=base_url, model=model)
        self.raw_client, self.model = client or configured, model or configured_model
        # Non-fixture tools must be explicitly installed by an embedding application.
        self.tool_map = tool_map or {"fs_read": fs_read, "fs_write": fs_write,
            "fs_delete": fs_delete, "net_fetch": net_fetch, "exec_cmd": exec_cmd}
        self.tool_definitions = copy.deepcopy(tool_definitions or
            [d for d in AGENT_TOOL_DEFINITIONS if d["function"]["name"] in self.tool_map])
        self.tool_dsl_name_map = {"fs_read":"fs.read", "fs_write":"fs.write",
            "fs_delete":"fs.delete", "net_fetch":"net.fetch", "exec_cmd":"exec",
            "git_push":"git.push", "memory_write":"memory.write", "memory_read":"memory.read"}
        self.event_callback = event_callback
        self.messages, self.trajectory, self._remaining_calls = [], [], []
        self._pending = None
        self.status, self.max_rounds, self.final_reply = "idle", 0, ""
        self.max_tool_calls, self.max_wall_seconds = max_tool_calls, max_wall_seconds
        self._tool_count, self._started = 0, None

    def _emit(self, kind, data):
        if self.event_callback:
            self.event_callback(kind, data)

    def _call_model(self, messages):
        if self.gateway:
            return self.gateway.chat_completion(model=self.model, messages=messages,
                tools=self.tool_definitions, temperature=0.0, max_tokens=1000)
        if self.raw_client is None:
            raise RuntimeError("No model credentials configured; live inference unavailable")
        # Baseline disables defense decisions, never protection of deployment credentials.
        from d2guard.redaction import OutboundRedactor
        safe=OutboundRedactor([getattr(self.raw_client,"api_key","")], detect_credentials=False).sanitize(dict(
            model=self.model,messages=messages,tools=self.tool_definitions,temperature=0.0,max_tokens=1000))
        return self.raw_client.chat.completions.create(**safe)

    def _dispatch_tool(self, tool_name, tool_args, call_id):
        self._emit('tool_call', dict(name=tool_name, args=copy.deepcopy(tool_args), call_id=call_id))
        start = time.perf_counter()
        details = dict(name=tool_name, dsl_name=self.tool_dsl_name_map.get(tool_name, tool_name),
                       args=copy.deepcopy(tool_args), call_id=call_id)
        func = self.tool_map.get(tool_name)
        if not func:
            details.update(success=False, blocked=False, verdict="ERROR", output="Unknown tool")
        elif self.hook:
            details.update(self.hook.execute_with_guard(details['dsl_name'], tool_args, func, call_id,
                source_type='WEB' if tool_name=='net_fetch' else 'LOCAL_FILE'))
        else:
            try:
                details.update(output=func(**tool_args), success=True, blocked=False, verdict="ALLOW")
            except Exception as exc:
                details.update(output=f"Tool failed: {type(exc).__name__}: {exc}",
                               success=False, blocked=False, verdict="ERROR")
        details['output'] = str(details['output'])
        details['elapsed_ms'] = (time.perf_counter()-start)*1000
        self._emit('tool_result', details)
        return details

    def _append_tool_result(self, details):
        self.messages.append(dict(role='tool', tool_call_id=details['call_id'],
                                  name=details['name'], content=details['output']))

    def _process_calls(self):
        while self._remaining_calls:
            if self._tool_count>=self.max_tool_calls or time.perf_counter()-self._started>=self.max_wall_seconds:
                self.status, self.final_reply='budget_exhausted','实际执行预算耗尽，保留已发生的工具和接收端证据'
                return False
            self._tool_count+=1
            call = self._remaining_calls.pop(0)
            try:
                args = json.loads(call.function.arguments)
                if not isinstance(args, dict):
                    raise ValueError('Arguments must be an object')
                details = self._dispatch_tool(call.function.name, args, call.id)
            except (ValueError, TypeError) as exc:
                details = dict(name=call.function.name, call_id=call.id, args={}, output='Invalid arguments',
                               verdict='ERROR', success=False, blocked=False, elapsed_ms=0)
            self.trajectory[-1]['tool_executions'].append(details)
            if details.get('pending'):
                self._pending = details
                self.status = 'pending_approval'
                return False
            self._append_tool_result(details)
        return True

    def _continue(self):
        while len(self.trajectory) < self.max_rounds:
            if time.perf_counter()-self._started>=self.max_wall_seconds:
                self.status, self.final_reply='budget_exhausted','实际执行预算耗尽'
                return self.result()
            round_num = len(self.trajectory) + 1
            self._emit('model_started', {'round': round_num})
            start = time.perf_counter()
            response = self._call_model(self.messages)
            msg = response.choices[0].message
            content = msg.content or ''
            calls = getattr(msg, 'tool_calls', None) or []
            entry = dict(round=round_num, thought=content,
                         model_latency_ms=(time.perf_counter()-start)*1000, tool_executions=[])
            self.trajectory.append(entry)
            # Serialize SDK messages, preserving tool-call arguments and IDs.
            if hasattr(msg, 'model_dump'):
                self.messages.append(msg.model_dump(exclude_none=True))
            else:
                self.messages.append(dict(role='assistant', content=content,
                    tool_calls=[dict(id=c.id, type='function', function=dict(name=c.function.name,
                                arguments=c.function.arguments)) for c in calls]))
            self._emit('model_completed', entry)
            self._emit('thought', dict(round=round_num, content=content))
            if not calls:
                self.status, self.final_reply = 'completed', content
                self._emit('agent_finish', dict(final_reply=content, status=self.status, round=round_num))
                return self.result()
            self._remaining_calls = list(calls)
            if not self._process_calls():
                return self.result()
        self.status, self.final_reply = 'max_rounds_reached', '已达最大循环轮次，任务完成情况需核验'
        self._emit('agent_finish', dict(final_reply=self.final_reply, status=self.status, round=len(self.trajectory)))
        return self.result()

    def run(self, user_prompt, max_rounds=6):
        system_prompts = {
            'd2_react': 'You are a helpful ReAct Agent. Use tools to complete the user task step by step. '
                        'Provide concise action summaries and thoughts; do not reveal private reasoning.',
            'pi_agent': 'You are an autonomous Pi Plan-and-Solve Agent. For each user task, formulate structured plan stages, '
                        'execute tools systematically to accomplish each stage, and verify outcomes.',
            'deepseek_harness': 'You are an engineering Agent operating within DeepSeek Harness. You strictly follow '
                                'an iterative observe-hypothesize-act-verify cycle and output concise Thoughts.'
        }
        sys_prompt = system_prompts.get(self.agent_framework, system_prompts['d2_react'])
        self.messages = [
            dict(role='system', content=sys_prompt),
            dict(role='user', content=user_prompt)
        ]
        self.trajectory, self._remaining_calls, self._pending = [], [], None
        self.max_rounds, self.status = max_rounds, 'running'
        self._tool_count, self._started = 0, time.perf_counter()
        self._emit('user_prompt', {'prompt': user_prompt, 'agent_framework': self.agent_framework, 'model': self.model})
        return self._continue()

    def resume(self, token_id, principal_id):
        if not self.hook or not self._pending or self._pending['approval_token']['token_id'] != token_id:
            raise ValueError('No matching suspended call')
        result = self.hook.resume(token_id, principal_id)
        details = {**self._pending, **result}
        self.trajectory[-1]['tool_executions'][-1] = details
        self._pending = None
        self._started=time.perf_counter()  # Approval waiting time is not model execution time.
        self._append_tool_result(details)
        self._emit('tool_resumed', details)
        if not self._process_calls():
            return self.result()
        return self._continue()

    def result(self):
        return dict(status=self.status, final_reply=self.final_reply,
                    trajectory=copy.deepcopy(self.trajectory), pending=copy.deepcopy(self._pending))
