"""
增量事件流交互式 HTML 攻击溯源与 MITRE ATLAS 矩阵大屏生成器 (ProvenanceDAG)
职责：
1. 从 D2GuardCore 事件流中提取因果拓扑链条；
2. 呈现时序执行序列与 Token/字符级定位 (Token-Level Attribution)；
3. 对齐国际权威 MITRE ATLAS 人工智能对抗威胁矩阵并动态点亮战术格；
4. 输出专业网安 SOC 级交互式可视化报告，支持节点下钻、字符级注入载荷对照与阻断复盘。
"""

from __future__ import annotations
import json
import os
import time
from typing import List
from .mitre_atlas import ATLAS_DATABASE, AtlasThreatMapper
from .models import D2Event


class ProvenanceDAGVisualizer:
    """因果溯源与 MITRE ATLAS 矩阵可视化大屏生成器"""

    @classmethod
    def generate_html(
        cls,
        events: List[D2Event],
        session_id: str = "demo_session",
        output_path: str = "provenance_report.html"
    ) -> str:
        """根据事件流生成自包含的 SOC 级交互式 HTML 溯源大屏"""

        nodes = []
        edges = []
        active_atlas_ids = set()

        # 遍历事件构建节点与边
        for idx, evt in enumerate(events):
            color = "#e3f2fd"  # 默认淡蓝
            border_color = "#1976d2"
            label = f"{evt.event_id}\n[{evt.tool_name or evt.event_type}]"

            # 威胁映射
            is_blocked = "BLOCK" in str(evt.raw_content) or "阻断" in str(evt.raw_content)
            atlas_tech = AtlasThreatMapper.map_policy_or_event(
                evt.tool_name, evt.tool_name, str(evt.raw_content)
            )
            if is_blocked:
                active_atlas_ids.add(atlas_tech.technique_id)
                color = "#ffebee"  # 红色阻断
                border_color = "#d32f2f"
            elif evt.source_type in ["WEB", "MCP"]:
                active_atlas_ids.add("AML.T0051")
                color = "#fff8e1"  # 橙黄色污染源
                border_color = "#f57c00"
            elif evt.stage.value == "TOOL_PRE_EXEC":
                color = "#f5f5f5"  # 灰色预执行
                border_color = "#757575"
            elif evt.stage.value == "TOOL_POST_EXEC":
                color = "#e8f5e9"  # 绿色执行完毕
                border_color = "#388e3c"

            node_meta = {
                "id": evt.event_id,
                "label": label,
                "shape": "box",
                "color": {"background": color, "border": border_color},
                "font": {"size": 13, "face": "system-ui, -apple-system, sans-serif"},
                "title": f"点击检视节点详情与 Token 归属",
                # 自定义下钻元数据
                "meta": {
                    "event_id": evt.event_id,
                    "stage": evt.stage.value,
                    "tool": evt.tool_name or "-",
                    "args": evt.tool_args or {},
                    "token_span": evt.token_span,
                    "source": evt.source_type,
                    "raw": evt.raw_content[:800],
                    "atlas": f"{atlas_tech.technique_id} - {atlas_tech.name}",
                    "is_blocked": is_blocked
                }
            }
            nodes.append(node_meta)

            # 构建连线
            if evt.parent_event_id:
                edges.append({
                    "from": evt.parent_event_id,
                    "to": evt.event_id,
                    "arrows": "to",
                    "color": {"color": "#455a64", "highlight": "#d32f2f"},
                    "width": 2
                })
            elif idx > 0 and not evt.parent_event_id:
                edges.append({
                    "from": events[idx - 1].event_id,
                    "to": evt.event_id,
                    "arrows": "to",
                    "dashes": True,
                    "color": {"color": "#b0bec5"},
                    "width": 1
                })

        # 构建 MITRE ATLAS 矩阵展示 HTML
        atlas_cards = []
        for tech_id, item in ATLAS_DATABASE.items():
            is_active = tech_id in active_atlas_ids
            badge_class = "atlas-badge active" if is_active else "atlas-badge inactive"
            status_text = "🚨 已检出并拦截" if is_active else "未检出活动"
            atlas_cards.append(f"""
            <div class="{badge_class}">
                <div class="atlas-id">{item.technique_id} · {item.severity}</div>
                <div class="atlas-name">{item.name}</div>
                <div class="atlas-status">{status_text}</div>
            </div>
            """)

        # 转换为表格行
        table_rows = []
        for evt in events:
            time_str = time.strftime('%H:%M:%S', time.localtime(evt.timestamp))
            table_rows.append(f"""
            <tr onclick="highlightNode('{evt.event_id}')">
                <td><code>{evt.event_id}</code></td>
                <td>{time_str}</td>
                <td><span class="badge stage-{evt.stage.value.lower()}">{evt.stage.value}</span></td>
                <td><strong>{evt.tool_name or '-'}</strong></td>
                <td><code>{json.dumps(evt.tool_args, ensure_ascii=False)[:50]}</code></td>
                <td><span class="token-tag">#{evt.token_span[0]}-#{evt.token_span[1]}</span></td>
                <td><span class="badge source-{evt.source_type.lower()}">{evt.source_type}</span></td>
            </tr>
            """)

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>D²Guard 智能体安全运营中心 (Agent-SOC) · 因果溯源与 MITRE ATLAS 矩阵</title>
    <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        :root {{
            --bg-main: #f8fafc;
            --card-bg: #ffffff;
            --border-color: #e2e8f0;
            --text-main: #1e293b;
            --text-muted: #64748b;
            --accent-blue: #0284c7;
            --danger: #ef4444;
            --success: #10b981;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg-main);
            color: var(--text-main);
            margin: 0;
            padding: 16px;
            font-size: 13.5px;
        }}
        .header {{
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: white;
            padding: 16px 24px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            margin-bottom: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .header h1 {{ margin: 0 0 6px 0; font-size: 20px; letter-spacing: -0.01em; }}
        .header p {{ margin: 0; opacity: 0.85; font-size: 13px; }}
        
        /* MITRE ATLAS 矩阵条 */
        .atlas-strip {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 12px;
            margin-bottom: 16px;
        }}
        .atlas-badge {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 10px 14px;
            display: flex;
            flex-direction: column;
            gap: 3px;
            transition: all 0.2s ease;
        }}
        .atlas-badge.active {{
            border-left: 4px solid var(--danger);
            background: #fff1f2;
        }}
        .atlas-badge.inactive {{
            opacity: 0.65;
            border-left: 4px solid #cbd5e1;
        }}
        .atlas-id {{ font-size: 11px; font-weight: 700; color: var(--text-muted); }}
        .atlas-name {{ font-size: 13px; font-weight: 600; color: var(--text-main); }}
        .atlas-status {{ font-size: 11px; font-weight: 600; color: var(--danger); }}
        .atlas-badge.inactive .atlas-status {{ color: var(--text-muted); }}

        .main-grid {{
            display: grid;
            grid-template-columns: 1.4fr 1.1fr;
            gap: 16px;
            height: calc(100vh - 220px);
            min-height: 580px;
        }}
        .panel {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.04);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}
        .panel-title {{
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
            font-weight: 700;
            font-size: 14px;
            background: #f1f5f9;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        #network {{ flex: 1; }}
        .table-container {{ flex: 1; overflow-y: auto; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
        th, td {{ padding: 8px 10px; text-align: left; border-bottom: 1px solid #f1f5f9; }}
        th {{ background-color: #f8fafc; position: sticky; top: 0; font-weight: 600; color: var(--text-muted); }}
        tr:hover {{ background-color: #f8fafc; cursor: pointer; }}
        .badge {{ padding: 2px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
        .stage-model_proposed {{ background: #e0f2fe; color: #0369a1; }}
        .stage-tool_pre_exec {{ background: #f1f5f9; color: #475569; }}
        .stage-tool_post_exec {{ background: #dcfce7; color: #15803d; }}
        .source-web {{ background: #fef3c7; color: #b45309; }}
        .source-user {{ background: #f3e8ff; color: #7e22ce; }}
        .token-tag {{ background: #ede9fe; color: #6d28d9; padding: 2px 5px; border-radius: 3px; font-family: monospace; }}

        /* 下钻详细视窗 */
        .diff-panel {{
            padding: 12px 16px;
            background: #fafafa;
            border-top: 1px solid var(--border-color);
            max-height: 200px;
            overflow-y: auto;
            font-size: 12.5px;
        }}
        .diff-header {{ font-weight: 700; margin-bottom: 6px; color: var(--accent-blue); }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>双镜 D²Guard · 智能体安全运营因果溯源大屏 (Agent-SOC)</h1>
            <p>会话 ID: <code>{session_id}</code> | 监控总线: MCP JSON-RPC 2.0 + Hook + API 网关 | 防护中枢: 快慢双系统与动态污点流</p>
        </div>
        <div style="text-align: right;">
            <span style="background: rgba(255,255,255,0.15); padding: 4px 10px; border-radius: 4px; font-size: 12px;">国赛赛题 5 官方规范对齐</span>
        </div>
    </div>

    <!-- 顶部 MITRE ATLAS 矩阵看板 -->
    <div class="atlas-strip">
        {"".join(atlas_cards)}
    </div>

    <div class="main-grid">
        <!-- 左侧: 交互式 DAG 拓扑图 -->
        <div class="panel">
            <div class="panel-title">
                <span>全链路因果溯源拓扑 (Causal Provenance DAG)</span>
                <span style="font-size: 12px; color: var(--text-muted); font-weight: normal;">支持滚轮缩放 / 拖拽节点 / 点击检视</span>
            </div>
            <div id="network"></div>
            <div class="diff-panel" id="diff-panel">
                <div class="diff-header" id="diff-title">💡 交互提示</div>
                <div id="diff-content" style="color: var(--text-muted);">点击上方任意节点，此处将展开对应的参数详情、Token 级来源归属与命中策略。</div>
            </div>
        </div>

        <!-- 右侧: 生命周期时序事件与 Token 级定位审计表 -->
        <div class="panel">
            <div class="panel-title">
                <span>时序生命周期事件与 Token 归属明细表</span>
                <span style="font-size: 12px; color: var(--text-muted); font-weight: normal;">共 {len(events)} 个因果事件节点</span>
            </div>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>事件 ID</th>
                            <th>时间</th>
                            <th>生命周期阶段</th>
                            <th>执行工具</th>
                            <th>调用参数摘要</th>
                            <th>Token区间</th>
                            <th>数据来源</th>
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
        var nodesArray = {json.dumps(nodes, ensure_ascii=False)};
        var edgesArray = {json.dumps(edges, ensure_ascii=False)};
        var nodes = new vis.DataSet(nodesArray);
        var edges = new vis.DataSet(edgesArray);
        var container = document.getElementById('network');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            layout: {{
                hierarchical: {{
                    direction: 'UD',
                    sortMethod: 'directed',
                    nodeSpacing: 180,
                    levelSeparation: 120
                }}
            }},
            physics: false,
            interaction: {{ hover: true, tooltipDelay: 200 }}
        }};
        var network = new vis.Network(container, data, options);

        function showNodeDetail(nodeData) {{
            if (!nodeData || !nodeData.meta) return;
            var m = nodeData.meta;
            var titleElem = document.getElementById('diff-title');
            var contentElem = document.getElementById('diff-content');
            titleElem.innerHTML = '🔍 节点检视: <b>' + m.event_id + '</b> [' + m.tool + '] ' + (m.is_blocked ? '<span style="color:#ef4444;">[已物理阻断]</span>' : '<span style="color:#10b981;">[合规放行]</span>');
            contentElem.innerHTML = 
                '<div><b>生命周期:</b> ' + m.stage + ' | <b>数据来源:</b> ' + m.source + ' | <b>Token 归属区间:</b> #' + m.token_span[0] + ' ~ #' + m.token_span[1] + '</div>' +
                '<div><b>MITRE ATLAS 关联技术:</b> <code>' + m.atlas + '</code></div>' +
                '<div style="margin-top:6px;"><b>调用参数/负载:</b> <pre style="background:#f1f5f9;padding:6px;border-radius:4px;overflow-x:auto;">' + JSON.stringify(m.args, null, 2) + '</pre></div>' +
                '<div><b>原始上下文片段:</b> <div style="font-family:monospace;background:#f8fafc;padding:6px;border-radius:4px;max-height:80px;overflow-y:auto;">' + (m.raw || '无') + '</div></div>';
        }}

        network.on("selectNode", function(params) {{
            if (params.nodes.length > 0) {{
                var selectedId = params.nodes[0];
                var node = nodesArray.find(function(n) {{ return n.id === selectedId; }});
                if (node) showNodeDetail(node);
            }}
        }});

        function highlightNode(nodeId) {{
            network.selectNodes([nodeId]);
            var node = nodesArray.find(function(n) {{ return n.id === nodeId; }});
            if (node) showNodeDetail(node);
        }}
    </script>
</body>
</html>
"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return output_path
