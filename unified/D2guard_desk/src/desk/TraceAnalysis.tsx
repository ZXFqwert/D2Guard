import { useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  MarkerType,
  Position,
  Node,
  Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Download,
  GitBranch,
  ListTree,
  FileLock2,
  Globe,
  GitFork,
  Fingerprint,
  MousePointer2,
} from "lucide-react";
import { DagNodeItem } from "../api/d2guardClient";
import { Run, download, ms, pct } from "./types";
import { Badge, Empty, PageHeading, Panel, Report } from "./ui";
function topology(items: DagNodeItem[], edges: { from: string; to: string }[]) {
  const ranks = new Map(items.map((n) => [n.id, 0]));
  const indegree = new Map(items.map((n) => [n.id, 0]));
  const children = new Map(items.map((n) => [n.id, [] as string[]]));
  edges.forEach((e) => {
    if (ranks.has(e.from) && ranks.has(e.to)) {
      children.get(e.from)!.push(e.to);
      indegree.set(e.to, indegree.get(e.to)! + 1);
    }
  });
  const queue = items.filter((n) => !indegree.get(n.id)).map((n) => n.id);
  while (queue.length) {
    const id = queue.shift()!;
    for (const child of children.get(id)!) {
      ranks.set(child, Math.max(ranks.get(child)!, ranks.get(id)! + 1));
      indegree.set(child, indegree.get(child)! - 1);
      if (!indegree.get(child)) queue.push(child);
    }
  }
  const slots = new Map<number, number>();
  return items.map((n) => {
    const rank = ranks.get(n.id)!;
    const slot = slots.get(rank) || 0;
    slots.set(rank, slot + 1);
    return { item: n, position: { x: rank * 270, y: slot * 140 } };
  });
}
export function TraceAnalysis({
  run,
  runs,
  selectedCall,
  onSelectRun,
}: {
  run?: Run;
  runs: Run[];
  selectedCall?: string;
  onSelectRun: (id: string) => void;
}) {
  const [view, setView] = useState<"dag" | "timeline">("dag");
  const [full, setFull] = useState(false);
  const [selected, setSelected] = useState<string | undefined>(
    selectedCall ? `call:${selectedCall}` : undefined,
  );
  useEffect(() => {
    setSelected(selectedCall ? `call:${selectedCall}` : undefined);
  }, [run?.id, selectedCall]);
  const telemetry = run?.telemetry;
  const { nodes, edges } = useMemo(() => {
    if (!telemetry) return { nodes: [], edges: [] };
    const items = telemetry.dag_nodes.filter(
      (n) => full || n.type !== "SOURCE" || n.label !== "host://workbench",
    );
    const ids = new Set(items.map((n) => n.id));
    const links = telemetry.dag_edges.filter(
      (e) => ids.has(e.from) && ids.has(e.to),
    );
    const nodes: Node[] = topology(items, links).map(({ item, position }) => ({
      id: item.id,
      position,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: {
        width: 218,
        height: 94,
        padding: 0,
        border: 0,
        background: "transparent",
      },
      data: {
        label: (
          <div
            className={`dag-node ${item.type.toLowerCase()} ${item.verdict?.toLowerCase() || ""} ${selected === item.id ? "selected" : ""}`}
          >
            <div>
              <span>
                {item.type === "AGENT" && item.label !== "main"
                  ? "SUB-AGENT"
                  : item.type.replace("_", " ")}
              </span>
              {item.verdict && <Badge value={item.verdict} />}
            </div>
            <strong title={item.label}>{item.label}</strong>
            <small>
              {item.token_span
                ? `Token #${item.token_span[0]} — #${item.token_span[1]}`
                : item.type === "TOOL"
                  ? "TOOL_PRE_EXEC"
                  : "真实调用节点"}
            </small>
          </div>
        ),
      },
    }));
    const edges: Edge[] = links.map((e, i) => {
      const color =
        e.edge_type === "TAINT_INDUCE"
          ? "#cc963f"
          : e.edge_type === "BLOCKED_ACTION"
            ? "#c55e59"
            : "#6596c5";
      return {
        id: `e-${i}`,
        source: e.from,
        target: e.to,
        type: "smoothstep",
        style: {
          stroke: color,
          strokeWidth: 1.6,
          ...(e.edge_type === "TAINT_INDUCE" ? { strokeDasharray: "5 5" } : {}),
        },
        markerEnd: { type: MarkerType.ArrowClosed, color },
      };
    });
    return { nodes, edges };
  }, [telemetry, full, selected]);
  const node = telemetry?.dag_nodes.find((n) => n.id === selected);
  const decision = run?.decisions.find(
    (d) => `call:${d.response.call_id}` === selected,
  );
  const uri =
    decision?.response.source_uri ||
    (node?.type === "SOURCE" ? node.label : undefined);
  const evidence =
    run?.evidence.find((e) =>
      node?.type === "SOURCE"
        ? `source:${e.event_id}` === node.id
        : e.uri === uri &&
          e.summary?.char_span.join(",") ===
            decision?.response.char_span?.join(","),
    ) || run?.evidence.find((e) => e.uri === uri);
  const span = decision?.response.char_span || evidence?.summary?.char_span;
  const tokenSpan =
    decision?.response.token_span ||
    evidence?.summary?.token_span ||
    node?.token_span;
  const raw =
    evidence?.raw ||
    (uri?.startsWith("user")
      ? telemetry?.anchor_intent?.initial_task
      : undefined);
  const chars = raw ? Array.from(raw) : [];
  const exportMarkdown = () => {
    if (!run || !telemetry) return;
    download(
      `D2Guard-${run.id}.md`,
      `# 双镜 D²Guard 复盘报告\n\n- 会话：${run.id}\n- 场景：${run.title}\n- 模式：${run.armor ? "双镜铠甲" : "裸机"}\n- 初始任务：${telemetry.anchor_intent?.initial_task || "未锁定"}\n\n## 裁决与解释\n\n${run.decisions.map((d) => `### ${d.tool} · ${d.final}\n\n${d.response.explainable_report}\n\n- 快镜：${ms(d.response.fast_mirror_label.latency_ms)}\n- 慢镜：${d.metric?.slow_latency_ms != null ? ms(d.metric.slow_latency_ms) : "未触发"}\n- char_span：${d.response.char_span?.join(", ")}\n- token_span：${d.response.token_span?.join(", ")}\n`).join("\n")}\n## 影响范围\n${Object.entries(
        telemetry.impact_scope,
      )
        .map(([k, v]) => `- ${k}：${v.join("、") || "无"}`)
        .join(
          "\n",
        )}\n\n## 调用图\n\n${telemetry.dag_nodes.map((n) => `- ${n.type} / ${n.label} / ${n.verdict || "—"}`).join("\n")}\n\n## 证据范围\n本报告反映真实内核裁决。演练不代表外部工具已执行。\n`,
      "text/markdown",
    );
  };
  const exportJsonl = () => {
    if (!run) return;
    const records = [
      { type: "session", id: run.id, title: run.title, armor: run.armor },
      ...run.decisions.map((d) => ({ type: "decision", ...d })),
      ...run.evidence.map((e) => ({ type: "evidence", ...e })),
      { type: "telemetry", ...telemetry },
    ];
    download(
      `D2Guard-${run.id}.jsonl`,
      records.map((r) => JSON.stringify(r)).join("\n") + "\n",
      "application/x-ndjson",
    );
  };
  return (
    <>
      <PageHeading
        eyebrow="TRACEABILITY & IMPACT"
        title="溯源与结果分析"
        detail="沿着证据回到源头，看清风险如何穿过每一个边界。"
      >
        <button disabled={!telemetry} onClick={exportMarkdown}>
          <Download size={15} />
          Markdown 报告
        </button>
        <button disabled={!telemetry} onClick={exportJsonl}>
          <Download size={15} />
          JSONL 证据
        </button>
      </PageHeading>
      <div className="trace-toolbar">
        <label>
          分析会话
          <select
            aria-label="分析会话"
            value={run?.id || ""}
            onChange={(e) => onSelectRun(e.target.value)}
          >
            {!runs.length && <option value="">暂无会话</option>}
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.started} · {r.title} · {r.armor ? "铠甲" : "裸机"}
              </option>
            ))}
          </select>
        </label>
        <div className="segmented">
          <button
            className={view === "dag" ? "selected" : ""}
            onClick={() => setView("dag")}
          >
            <GitBranch size={15} />
            DAG 拓扑图
          </button>
          <button
            className={view === "timeline" ? "selected" : ""}
            onClick={() => setView("timeline")}
          >
            <ListTree size={15} />
            时序链路
          </button>
        </div>
      </div>
      {!telemetry ? (
        <div className="panel">
          <Empty
            title="还没有可以回溯的行动"
            detail="前往工作台完成一次演练，调用图、证据与影响范围会同步到这里。"
          />
        </div>
      ) : (
        <>
          <div className={`trace-layout ${node ? "with-inspector" : ""}`}>
            <section className="panel graph-panel">
              <div className="panel-head">
                <div>
                  <h3>
                    {view === "dag"
                      ? "跨 MCP 与子 Agent 因果拓扑"
                      : "全链路时序瀑布流"}
                  </h3>
                  <p>
                    {telemetry.dag_nodes.length} 个节点 ·{" "}
                    {telemetry.dag_edges.length} 条真实关系
                  </p>
                </div>
                {view === "dag" && (
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={full}
                      onChange={(e) => setFull(e.target.checked)}
                    />
                    完整生命周期
                  </label>
                )}
              </div>
              <div className="graph-legend">
                <span>
                  <i className="blue-line" />
                  真实调用
                </span>
                <span>
                  <i className="orange-line" />
                  污点诱导
                </span>
                <span>
                  <i className="red-line" />
                  阻断动作
                </span>
                <small>拖动画布 · 滚轮缩放 · 点击节点检查证据</small>
              </div>
              {view === "dag" ? (
                <div className="graph-canvas" data-testid="dag-canvas">
                  <ReactFlow
                    key={`${run.id}-${full}`}
                    nodes={nodes}
                    edges={edges}
                    fitView
                    fitViewOptions={{ padding: 0.06 }}
                    minZoom={0.12}
                    maxZoom={1.7}
                    nodesDraggable={false}
                    nodesConnectable={false}
                    onNodeClick={(_, n) => setSelected(n.id)}
                    proOptions={{ hideAttribution: true }}
                  >
                    <Background color="#dce4df" gap={24} size={1} />
                    <Controls showInteractive={false} />
                  </ReactFlow>
                </div>
              ) : (
                <div className="timeline-view">
                  {run.logs.map((l, i) => {
                    const idx =
                      run.logs
                        .slice(0, i + 1)
                        .filter((x) => x.type === "HOOK_VERDICT").length - 1;
                    const d =
                      l.type === "HOOK_VERDICT"
                        ? run.decisions[idx]
                        : undefined;
                    return (
                      <button
                        key={l.id}
                        className={`timeline-row ${l.type.toLowerCase()}`}
                        onClick={() => {
                          if (d) setSelected(`call:${d.response.call_id}`);
                          else {
                            const source = telemetry.dag_nodes.find(
                              (n) =>
                                n.label ===
                                l.title.replace("测试证据已摄入：", ""),
                            );
                            if (source) setSelected(source.id);
                          }
                        }}
                      >
                        <time>{l.timestamp}</time>
                        <span className="timeline-point" />
                        <div>
                          <small>
                            {l.type === "THOUGHT" ? "公开执行计划" : l.type}
                          </small>
                          <strong>{l.title}</strong>
                          {d && (
                            <div className="waterfall">
                              <span
                                style={{
                                  width: `${Math.max(5, Math.min(100, (d.elapsed / Math.max(1, ...run.decisions.map((x) => x.elapsed))) * 100))}%`,
                                }}
                              />
                              <small>
                                Hook 全流程 {ms(d.elapsed)}（含审批等待）
                              </small>
                            </div>
                          )}
                        </div>
                        {l.verdict && <Badge value={l.verdict} />}
                      </button>
                    );
                  })}
                </div>
              )}
            </section>
            {node && (
              <aside className="panel evidence-inspector">
                <div className="panel-head">
                  <h3>节点证据检查器</h3>
                  <button
                    className="icon-button"
                    aria-label="关闭检查器"
                    onClick={() => setSelected(undefined)}
                  >
                    ×
                  </button>
                </div>
                <div className="inspector-body">
                  <span className="subtle-tag">{node.type}</span>
                  <h3>{node.label}</h3>
                  {node.verdict && <Badge value={node.verdict} />}
                  <h4>完整调用参数</h4>
                  {decision ? (
                    <pre>{JSON.stringify(decision.args, null, 2)}</pre>
                  ) : (
                    <p className="muted small">
                      {node.type === "TOOL"
                        ? "本地会话未保留该调用的参数"
                        : "此节点是来源或执行主体；工具参数见关联 TOOL 节点。"}
                    </p>
                  )}
                  <h4>匹配策略</h4>
                  <code>
                    {decision?.response.matched_policy_id ||
                      "未命中硬策略 / 非裁决节点"}
                  </code>
                  <h4>
                    <Fingerprint size={15} />
                    文本与 Token 染色
                  </h4>
                  <p className="small muted">{uri || "无独立文本来源"}</p>
                  <div className="span-labels">
                    <code>char_span {span ? `[${span.join(", ")}]` : "—"}</code>
                    <code>
                      token_span{" "}
                      {tokenSpan ? `[#${tokenSpan[0]}, #${tokenSpan[1]}]` : "—"}
                    </code>
                  </div>
                  {raw ? (
                    <pre className="highlighted-text">
                      {span ? (
                        <>
                          {chars.slice(0, span[0]).join("")}
                          <mark>{chars.slice(span[0], span[1]).join("")}</mark>
                          {chars.slice(span[1]).join("")}
                        </>
                      ) : (
                        raw
                      )}
                    </pre>
                  ) : (
                    <p className="muted small">
                      此节点没有可用原文；展示内核返回的区间，不推测文本。
                    </p>
                  )}
                  {evidence?.raw_tokens && (
                    <>
                      <h4>原文 Token 映射</h4>
                      <div className="token-map">
                        {evidence.raw_tokens.map(([a, b], i) => (
                          <span
                            key={i}
                            className={
                              tokenSpan && i >= tokenSpan[0] && i < tokenSpan[1]
                                ? "tainted"
                                : ""
                            }
                            title={`Token #${i} · 字符 [${a}, ${b})`}
                          >
                            <small>#{i}</small>
                            {chars.slice(a, b).join("")}
                          </span>
                        ))}
                      </div>
                    </>
                  )}
                  {decision && (
                    <>
                      <h4>可解释研判</h4>
                      <Report text={decision.response.explainable_report} />
                    </>
                  )}
                </div>
              </aside>
            )}
          </div>
          <div className="impact-grid">
            {[
              ["protected_files", "受保护敏感文件", FileLock2],
              ["blocked_domains", "已阻断外发域名", Globe],
              ["blocked_git_repos", "防篡改 Git 仓库", GitFork],
            ].map(([key, label, Icon]) => {
              const values =
                telemetry.impact_scope[
                  key as keyof typeof telemetry.impact_scope
                ];
              const I = Icon as typeof FileLock2;
              return (
                <div className="panel impact-card" key={String(key)}>
                  <I size={19} />
                  <strong>{values.length}</strong>
                  <h3>{String(label)}</h3>
                  {values.length ? (
                    values.map((v) => <code key={v}>{v}</code>)
                  ) : (
                    <p>本会话暂无记录</p>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
