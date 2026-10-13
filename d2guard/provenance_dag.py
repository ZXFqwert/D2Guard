"""
增量事件流交互式 HTML 攻击溯源 DAG 生成器 (ProvenanceDAG)
职责：
1. 从 D2GuardCore 事件流中提取因果拓扑链条；
2. 呈现时序执行序列与 Token/字符级定位；
3. 输出高可视化、自包含、支持缩放拖拽的交互式 HTML 报告；
4. 直观呈现阻断断点、受污染源头与凭证隔离边界。
"""

from __future__ import annotations
import json
import os
import time
from typing import List
from .models import D2Event


class ProvenanceDAGVisualizer:
    """因果溯源 DAG 可视化生成器"""

    @classmethod
    def generate_html(
        cls,
        events: List[D2Event],
        session_id: str = "demo_session",
        output_path: str = "provenance_report.html"
    ) -> str:
        """根据事件流生成独立的交互式 HTML 溯源页面"""

        nodes = []
        edges = []

        # 遍历事件构建节点与边
        for idx, evt in enumerate(events):
            color = "#90caf9"  # 默认蓝色
            border_color = "#1e88e5"
            label = f"{evt.event_id}\n[{evt.tool_name or evt.event_type}]"

            # 区分节点颜色
            if "BLOCK" in str(evt.raw_content) or "阻断" in str(evt.raw_content):
                color = "#ef9a9a"  # 红色阻断
                border_color = "#c62828"
            elif evt.source_type == "WEB":
                color = "#ffe082"  # 橙黄色污染源
                border_color = "#f57c00"
            elif evt.stage.value == "TOOL_PRE_EXEC":
                color = "#b0bec5"  # 灰色预执行
                border_color = "#546e7a"
            elif evt.stage.value == "TOOL_POST_EXEC":
                color = "#a5d6a7"  # 绿色执行完毕
                border_color = "#2e7d32"

            node = {
                "id": evt.event_id,
                "label": label,
                "shape": "box",
                "color": {"background": color, "border": border_color},
                "font": {"size": 13, "face": "Arial"},
                "title": f"<b>{evt.event_id}</b><br>阶段: {evt.stage}<br>工具: {evt.tool_name}<br>参数: {json.dumps(evt.tool_args, ensure_ascii=False)}<br>Token区间: {evt.token_span}"
            }
            nodes.append(node)

            # 构建父子连线
            if evt.parent_event_id:
                edges.append({
                    "from": evt.parent_event_id,
                    "to": evt.event_id,
                    "arrows": "to",
                    "color": {"color": "#616161"}
                })
            elif idx > 0 and not evt.parent_event_id:
                # 默认时序虚线连接
                edges.append({
                    "from": events[idx - 1].event_id,
                    "to": evt.event_id,
                    "arrows": "to",
                    "dashes": True,
                    "color": {"color": "#b0bec5"}
                })

        # 转换为表格行
        table_rows = []
        for evt in events:
            time_str = time.strftime('%H:%M:%S', time.localtime(evt.timestamp))
            table_rows.append(f"""
            <tr>
                <td><code>{evt.event_id}</code></td>
                <td>{time_str}</td>
                <td><span class="badge stage-{evt.stage.value.lower()}">{evt.stage.value}</span></td>
                <td><strong>{evt.tool_name or '-'}</strong></td>
                <td><code>{json.dumps(evt.tool_args, ensure_ascii=False)[:60]}</code></td>
                <td><span class="token-tag">#{evt.token_span[0]}-#{evt.token_span[1]}</span></td>
                <td><span class="badge source-{evt.source_type.lower()}">{evt.source_type}</span></td>
            </tr>
            """)

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>双镜 D²Guard 攻击因果溯源大屏 - {session_id}</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #f4f6f9;
            margin: 0;
            padding: 20px;
            color: #333;
        }}
        .header {{
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            color: white;
            padding: 20px 30px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .header h1 {{ margin: 0 0 10px 0; font-size: 24px; }}
        .header p {{ margin: 0; opacity: 0.9; font-size: 14px; }}
        .container {{ display: flex; gap: 20px; height: 750px; }}
        .dag-panel {{
            flex: 1.3;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08);
            display: flex;
            flex-direction: column;
        }}
        .table-panel {{
            flex: 1.1;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}
        .panel-title {{
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
            font-weight: bold;
            font-size: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        #network {{ flex: 1; }}
        .table-container {{ flex: 1; overflow-y: auto; padding: 10px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
        th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid #f0f0f0; }}
        th {{ background-color: #fafafa; position: sticky; top: 0; }}
        .badge {{ padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 500; }}
        .stage-model_proposed {{ background: #e3f2fd; color: #1565c0; }}
        .stage-tool_pre_exec {{ background: #f5f5f5; color: #616161; }}
        .stage-tool_post_exec {{ background: #e8f5e9; color: #2e7d32; }}
        .source-web {{ background: #fff8e1; color: #f57f17; }}
        .source-user {{ background: #f3e5f5; color: #7b1fa2; }}
        .token-tag {{ background: #ede7f6; color: #512da8; padding: 2px 5px; border-radius: 3px; font-family: monospace; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>双镜 D²Guard (D2Guard) 攻击因果拓扑与时序溯源全景大屏</h1>
        <p>会话 ID: {session_id} | 监控探针: 工具侧 Hook + API 侧网关 | 决策中枢: 共享防护内核 (快镜 Laya + 慢镜 DeepSeek)</p>
    </div>

    <div class="container">
        <div class="dag-panel">
            <div class="panel-title">
                <span>因果图谱 (DAG Topology)</span>
                <span style="font-size: 12px; color: #666;">支持滚轮缩放与节点拖拽</span>
            </div>
            <div id="network"></div>
        </div>

        <div class="table-panel">
            <div class="panel-title">
                <span>生命周期事件流与 Token 级定位审计</span>
                <span style="font-size: 12px; color: #666;">共 {len(events)} 个增量事件</span>
            </div>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>事件 ID</th>
                            <th>时间</th>
                            <th>阶段</th>
                            <th>工具</th>
                            <th>参数摘要</th>
                            <th>Token区间</th>
                            <th>来源</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(table_rows)}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script type="text/javascript">
        var nodes = new vis.DataSet({json.dumps(nodes, ensure_ascii=False)});
        var edges = new vis.DataSet({json.dumps(edges, ensure_ascii=False)});
        var container = document.getElementById('network');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            layout: {{
                hierarchical: {{
                    direction: 'UD',
                    sortMethod: 'directed',
                    nodeSpacing: 160,
                    levelSeparation: 110
                }}
            }},
            physics: false,
            interaction: {{ hover: true, tooltipDelay: 200 }}
        }};
        var network = new vis.Network(container, data, options);
    </script>
</body>
</html>
"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return output_path
