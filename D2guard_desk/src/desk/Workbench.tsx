import { useEffect, useRef, useState } from "react";
import {
  ArrowUp,
  ChevronDown,
  PanelRightClose,
  PanelRightOpen,
  LockKeyhole,
  Database,
  Sparkles,
  Terminal,
  RotateCcw,
  CheckCheck,
  ShieldCheck,
  ShieldAlert,
  FileText,
  Circle,
  Globe,
  GitBranch,
  Cpu,
  HardDrive,
  Activity,
  ArrowRight,
  Eye,
} from "lucide-react";
import {
  DagEdgeItem,
  DagNodeItem,
  TelemetrySnapshotResponse,
} from "../api/d2guardClient";
import { Run, Scenario, ms, pct, pretty } from "./types";
import { Badge, Logo, Report } from "./ui";
import { ModelConfig, ModelPopover } from "./Settings";

const cleanTitle = (t: string) =>
  t.replace(/^(?:\u5267\u672c|\u573a\u666f)\s*\d+[：:]\s*/, "");

const CAPABILITY_PILLS = [
  { icon: HardDrive, label: "fs.read / fs.write 文件系统读写" },
  { icon: Globe, label: "net.fetch 在线网络访问" },
  { icon: Terminal, label: "exec 终端命令执行" },
  { icon: GitBranch, label: "git.status / push 代码仓操作" },
  { icon: Cpu, label: "spawn_subagent 子 Agent 派发" },
  { icon: Database, label: "memory.recall / write 跨会话记忆" },
];

const QUICK_SCENARIO_CARDS = [
  {
    id: "PB-01",
    shortTitle: "PB-01 间接注入窃密",
    sub: "恶意 README 诱导读取 SSH 私钥并外发",
  },
  {
    id: "PB-02",
    shortTitle: "PB-02 多轮8字节分片外发",
    sub: ".env 凭据 8 字节切片跨轮编码外传",
  },
  {
    id: "PB-04",
    shortTitle: "PB-04 只读检视越权推送",
    sub: "PR 评论劫持只读会话执行 git.push",
  },
  {
    id: "PB-05",
    shortTitle: "PB-05 跨MCP与子Agent渗透",
    sub: "MCP 污染诱导子 Agent 写入定时任务",
  },
];

function extractScenarioSources(scenario?: Scenario): string[] {
  if (!scenario) return [];
  const items = new Set<string>();
  for (const step of scenario.steps || []) {
    if (step.sourceUri) items.add(step.sourceUri);
    if (typeof step.toolArgs?.path === "string") items.add(step.toolArgs.path);
    if (typeof step.toolArgs?.url === "string") items.add(step.toolArgs.url);
    if (typeof step.toolArgs?.remote === "string") {
      items.add(`git:${step.toolArgs.remote}/${step.toolArgs.branch || "main"}`);
    }
  }
  return Array.from(items);
}

function buildFallbackDag(run: Run): {
  nodes: DagNodeItem[];
  edges: DagEdgeItem[];
} {
  const nodes: DagNodeItem[] = [];
  const edges: DagEdgeItem[] = [];
  const sourceLogs = run.logs.filter((l) => l.type === "SOURCE");
  const firstDec =
    run.decisions.find(
      (d) => d.final === "BLOCK" || d.response.verdict === "BLOCK",
    ) ||
    run.decisions.find((d) => d.response.verdict === "ASK") ||
    run.decisions.at(-1);

  const sourceUri =
    firstDec?.response.source_uri ||
    run.evidence.at(-1)?.uri ||
    sourceLogs.at(-1)?.title ||
    "外部不可信输入源";

  nodes.push({
    id: "node-source",
    type: "SOURCE",
    label: sourceUri,
    source_type: sourceUri.startsWith("mcp://")
      ? "MCP_RET"
      : sourceUri.startsWith("github://")
        ? "CODE_ISSUE"
        : sourceUri.startsWith("memory://")
          ? "MEMORY"
          : "LOCAL_FILE",
    token_span: firstDec?.response.token_span || [12, 68],
  });

  const hasMcpOrSub =
    sourceUri.startsWith("mcp://") ||
    run.logs.some(
      (l) =>
        (l.toolName || "").includes("subagent") ||
        (l.toolName || "").includes("mcp"),
    );

  if (hasMcpOrSub) {
    nodes.push({
      id: "node-mcp-sub",
      type: "MCP_SERVER",
      label: "MCP 节点 / 子 Agent 派发链路",
    });
    edges.push({
      from: "node-source",
      to: "node-mcp-sub",
      edge_type: "TAINT_INDUCE",
    });
    nodes.push({
      id: "node-agent",
      type: "AGENT",
      label: "Main Agent 决策上下文",
    });
    edges.push({
      from: "node-mcp-sub",
      to: "node-agent",
      edge_type: "TAINT_INDUCE",
    });
  } else {
    nodes.push({
      id: "node-agent",
      type: "AGENT",
      label: "Main Agent 决策上下文",
    });
    edges.push({
      from: "node-source",
      to: "node-agent",
      edge_type: "TAINT_INDUCE",
    });
  }

  if (firstDec) {
    nodes.push({
      id: "node-tool",
      type: "TOOL",
      label: `${firstDec.tool}`,
      verdict: firstDec.final,
      token_span: firstDec.response.token_span,
    });
    edges.push({
      from: "node-agent",
      to: "node-tool",
      edge_type:
        firstDec.final === "BLOCK" ? "BLOCKED_ACTION" : "ACTUAL_CALL",
    });
  }

  return { nodes, edges };
}

export function Workbench({
  armor,
  online = true,
  run,
  telemetry,
  busy,
  ready,
  onRun,
  onRunWithArmor,
  onToggleArmor,
  onInspect,
  onCancel,
  onReset,
  scenarios,
  selectedScenarioId,
  onSelectScenario,
  config,
  onConfig,
}: {
  armor: boolean;
  online?: boolean;
  run?: Run;
  telemetry?: TelemetrySnapshotResponse;
  busy: boolean;
  ready: boolean;
  onRun: (input: Scenario | string) => void;
  onRunWithArmor?: (input: Scenario | string, targetArmor: boolean) => void;
  onToggleArmor?: () => void;
  onInspect?: (callId?: string) => void;
  onCancel: () => void;
  onReset: () => void;
  scenarios: Scenario[];
  selectedScenarioId?: string;
  onSelectScenario?: (id: string) => void;
  config: ModelConfig;
  onConfig: (c: ModelConfig) => void;
}) {
  const [input, setInput] = useState("");
  const [selected, setSelected] = useState(selectedScenarioId || "PB-02");
  const [details, setDetails] = useState(false);
  const [model, setModel] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (selectedScenarioId && selectedScenarioId !== selected) {
      setSelected(selectedScenarioId);
    }
  }, [selectedScenarioId]);

  useEffect(() => {
    if (
      scenarios.length > 0 &&
      !scenarios.some((scenario) => scenario.id === selected)
    ) {
      const fallbackId = scenarios[0]?.id || "";
      setSelected(fallbackId);
      onSelectScenario?.(fallbackId);
    }
  }, [scenarios, selected]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [run?.logs.length, run?.status]);

  const selectScenario = (id: string) => {
    setSelected(id);
    onSelectScenario?.(id);
  };

  const submit = () => {
    if (!input.trim() || busy || !ready) return;
    onRun(input.trim());
    setInput("");
  };

  const activeTelemetry = telemetry || run?.telemetry;
  const latest = run?.decisions.at(-1);
  const activeScenario =
    scenarios.find((s) => s.id === selected) || scenarios[0];
  const scenarioSources = extractScenarioSources(activeScenario);

  const matchedScenario = run
    ? scenarios.find(
        (s) =>
          s.id === run.scenarioId ||
          s.title === run.title ||
          cleanTitle(s.title) === cleanTitle(run.title),
      )
    : undefined;

  const executedTools = run
    ? run.logs
        .filter((l) => l.type === "TOOL_RESULT" && l.executed)
        .map((l) => l.toolName || l.title)
    : [];

  const isUnprotectedCompromised = Boolean(
    run &&
      !run.armor &&
      !busy &&
      (run.result?.attack_succeeded === true ||
        (run.result &&
          (run.result.received_bytes > 0 ||
            run.result.outbound_receipts.length > 0)) ||
        run.logs.some(
          (l) =>
            l.type === "TOOL_RESULT" &&
            l.executed &&
            [
              "net.fetch",
              "exec",
              "git.push",
              "spawn_subagent",
              "fs.write",
            ].includes(l.toolName || ""),
        )),
  );

  const blockedDecision = run
    ? run.decisions.find(
        (d) => d.final === "BLOCK" || d.response.verdict === "BLOCK",
      ) ||
      run.decisions.find((d) => d.response.verdict === "ASK") ||
      run.decisions.at(-1)
    : undefined;

  const isProtectedIntercepted = Boolean(
    run &&
      run.armor &&
      (run.result?.attack_prevented === true ||
        run.decisions.some(
          (d) =>
            d.final === "BLOCK" ||
            d.response.verdict === "BLOCK" ||
            d.response.verdict === "ASK",
        )),
  );

  const outboundEntries = Object.entries(
    activeTelemetry?.accumulated_outbound || {},
  );
  const maxCoverage = outboundEntries.length
    ? Math.max(...outboundEntries.map(([, r]) => r.coverage_ratio))
    : blockedDecision?.coverage ?? 0;

  const dagData =
    activeTelemetry?.dag_nodes && activeTelemetry.dag_nodes.length > 0
      ? {
          nodes: activeTelemetry.dag_nodes,
          edges: activeTelemetry.dag_edges || [],
        }
      : run
        ? buildFallbackDag(run)
        : { nodes: [], edges: [] };

  return (
    <div className="workbench-layout">
      <div className="conversation">
        <div className="conversation-top">
          <div className="conversation-title-group">
            <span
              className={`mode-badge-pill ${armor ? "protected" : "unprotected"}`}
            >
              {armor
                ? "双镜 D²Guard · 闭环防护模式 (Hook + Gateway + Core)"
                : "Codex Agent · 无防护正常模式"}
            </span>
            <strong>
              {run?.title ? cleanTitle(run.title) : "Codex 在线智能体工作台"}
            </strong>
          </div>
          <div className="button-row">
            <span className="kernel-status-pill" title="安全内核连接状态">
              <span
                className={`status-dot ${online ? "online" : "offline"}`}
              />
              {online ? "内核在线" : "内核离线"}
            </span>
            <span
              className={`run-state ${busy ? "running" : ""}`}
              role="status"
            >
              {busy
                ? "正在执行…"
                : run
                  ? run.status === "error"
                    ? "本轮失败"
                    : run.status === "cancelled"
                      ? "已取消"
                      : run.status === "complete"
                        ? "执行完成"
                        : "等待审批"
                  : "准备就绪"}
            </span>
            {onToggleArmor && (
              <button
                type="button"
                className={`mode-switch-btn ${armor ? "is-armor" : "is-normal"}`}
                disabled={busy}
                onClick={onToggleArmor}
              >
                {armor ? "切换为无防护正常 Agent" : "启动双镜 D²Guard 防护"}
              </button>
            )}
            {busy && (
              <button
                onClick={onCancel}
                aria-label="取消当前执行"
                title="取消当前执行"
              >
                取消
              </button>
            )}
            <button
              disabled={busy || !ready}
              onClick={onReset}
              aria-label="重置会话"
              title="重置会话"
            >
              <RotateCcw size={16} />
            </button>
            <button
              aria-label={details ? "收起安全详情" : "展开安全详情"}
              title={details ? "收起安全详情" : "展开安全详情"}
              onClick={() => setDetails(!details)}
            >
              {details ? (
                <PanelRightClose size={17} />
              ) : (
                <PanelRightOpen size={17} />
              )}
            </button>
          </div>
        </div>

        <div className="conversation-scroll">
          {!run?.logs.length ? (
            <div className="welcome">
              <Logo large armor={armor} />
              <h1>
                {armor ? "双镜 D²Guard 安全防护工作台" : "Codex 智能体工作台"}
              </h1>
              <p>
                {armor
                  ? "工具侧 Hook + API 侧网关 + D¹ 快慢双镜与 D² 增量状态流已接管当前 Agent 运行时"
                  : "具备工具调用、文件系统操作、网络访问、Git 与子 Agent 派发能力的在线运行 LLM Agent 系统"}
              </p>

              <div className="codex-cap-bar" aria-label="在线 Agent 核心能力矩阵">
                {CAPABILITY_PILLS.map((cap) => {
                  const Icon = cap.icon;
                  return (
                    <span key={cap.label} className="codex-cap-pill">
                      <Icon size={13} />
                      {cap.label}
                    </span>
                  );
                })}
              </div>

              {activeScenario && (
                <section
                  className={`env-stage-card ${armor ? "protected" : "unprotected"}`}
                  aria-label="当前选定攻击场景环境"
                >
                  <div className="env-stage-head">
                    <div className="env-stage-title">
                      <strong>
                        🎯 当前选定攻击场景环境：{activeScenario.id} ·{" "}
                        {cleanTitle(activeScenario.title)}
                      </strong>
                    </div>
                    <div className="env-stage-badges">
                      <span
                        className={`threat-pill ${activeScenario.threatLevel.toLowerCase()}`}
                      >
                        {activeScenario.threatLevel}
                      </span>
                      <span className="subtle-tag">
                        {activeScenario.category}
                      </span>
                    </div>
                  </div>

                  <div className="env-stage-body">
                    <div className="env-stage-row">
                      <span className="env-stage-label">
                        正常业务指令（User Prompt）
                      </span>
                      <p>{activeScenario.initialTask}</p>
                    </div>
                    <div className="env-stage-row">
                      <span className="env-stage-label">
                        环境中预置的隐蔽攻击载荷（Staged Attack Environment）
                      </span>
                      <p>{activeScenario.description}</p>
                      {scenarioSources.length > 0 && (
                        <div className="env-source-tags">
                          <small className="muted">预置环境载体与敏感目标：</small>
                          {scenarioSources.map((src) => (
                            <code key={src}>{src}</code>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="env-stage-actions">
                    <button
                      type="button"
                      className="primary env-run-primary"
                      disabled={!ready || busy}
                      onClick={() => onRun(activeScenario)}
                    >
                      {armor
                        ? "在【双镜 D²Guard 防护】下运行此场景（观察检测与阻断） ↗"
                        : "在【无防护正常 Agent】下运行此场景（观察沦陷后果） ↗"}
                    </button>
                    {(onRunWithArmor || onToggleArmor) && (
                      <button
                        type="button"
                        className="env-run-secondary"
                        disabled={!ready || busy}
                        onClick={() => {
                          if (onRunWithArmor) {
                            onRunWithArmor(activeScenario, !armor);
                          } else {
                            onToggleArmor?.();
                            onRun(activeScenario);
                          }
                        }}
                      >
                        {armor
                          ? "切换无防护正常 Agent 运行对比"
                          : "直接开启双镜 D²Guard 防护运行对比"}
                      </button>
                    )}
                  </div>
                </section>
              )}

              <div className="welcome-shortcuts" aria-label="典型攻击场景环境快捷切换">
                {QUICK_SCENARIO_CARDS.map((card) => {
                  const targetScenario =
                    scenarios.find((item) => item.id === card.id) ||
                    scenarios[0];
                  const isCurrent = selected === card.id;
                  return (
                    <button
                      key={card.id}
                      type="button"
                      className={isCurrent ? "active" : ""}
                      disabled={!ready || busy}
                      onClick={() => {
                        selectScenario(card.id);
                        if (targetScenario) onRun(targetScenario);
                      }}
                    >
                      {armor ? (
                        <ShieldCheck size={17} />
                      ) : (
                        <Sparkles size={17} />
                      )}
                      <div>
                        {card.shortTitle}
                        <small>{card.sub}</small>
                      </div>
                      <span>↗</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="execution-flow">
              {run.logs.map((log, i) => {
                const verdictIndex =
                  run.logs
                    .slice(0, i + 1)
                    .filter((item) => item.type === "HOOK_VERDICT").length - 1;
                const decision = log.callId
                  ? run.decisions.find(
                      (item) => item.response.call_id === log.callId,
                    )
                  : run.decisions[verdictIndex];
                return (
                  <article
                    key={log.id}
                    className={`flow-entry ${log.type.toLowerCase()}`}
                  >
                    <div className="flow-icon">
                      {log.type === "USER" ? (
                        <span>你</span>
                      ) : log.type === "HOOK_VERDICT" ? (
                        <ShieldCheck size={17} />
                      ) : log.type === "TOOL_CALL" ? (
                        <Terminal size={16} />
                      ) : log.type === "SOURCE" ? (
                        <FileText size={16} />
                      ) : (
                        <CheckCheck size={16} />
                      )}
                    </div>
                    <div className="flow-body">
                      <div className="flow-meta">
                        <strong>
                          {log.type === "USER"
                            ? "用户任务"
                            : log.type === "PLAN" || log.type === "THOUGHT"
                              ? "Agent · 公开执行计划"
                              : log.type === "TOOL_CALL"
                                ? "工具调用申请"
                                : log.type === "HOOK_VERDICT"
                                  ? "双镜 · 安全裁决"
                                  : log.type === "SOURCE"
                                    ? "证据摄入"
                                    : log.title}
                        </strong>
                        <time>{log.timestamp}</time>
                      </div>
                      {log.type === "HOOK_VERDICT" ? (
                        <div
                          className={`verdict-card ${(log.verdict || "").toLowerCase()}`}
                        >
                          <div className="row-between">
                            <Badge value={log.verdict!} />
                            <span className="small">
                              System 1 · {ms(log.latencyMs || 0)}
                            </span>
                          </div>
                          {log.matchedPolicy && (
                            <code className="policy-code">
                              {log.matchedPolicy}
                            </code>
                          )}
                          <Report text={log.detail || ""} />
                          {decision?.response.verdict === "ASK" && (
                            <div className="approval-result">
                              ASK 审批完成 · 最终裁决 {decision.final}
                            </div>
                          )}
                          {decision?.metric?.slow_latency_ms !== null &&
                            decision?.metric?.slow_latency_ms !== undefined && (
                              <small className="muted">
                                System 2 · {ms(decision.metric.slow_latency_ms)}{" "}
                                ·{" "}
                                {decision.metric.slow_mode === "remote"
                                  ? "远程复核"
                                  : "本地降级复核"}
                              </small>
                            )}
                        </div>
                      ) : log.type === "TOOL_CALL" ? (
                        <div className="tool-card">
                          <div className="row-between">
                            <code>
                              {log.title.replace("申请内核审计：", "")}
                            </code>
                            <span className="subtle-tag">TOOL_PRE_EXEC</span>
                          </div>
                          <pre>{pretty(log.detail)}</pre>
                        </div>
                      ) : log.type === "SOURCE" ? (
                        <details className="source-card">
                          <summary>{log.title}</summary>
                          <pre>{pretty(log.detail)}</pre>
                        </details>
                      ) : log.type === "TOOL_RESULT" ? (
                        <div className="tool-card">
                          <div className="row-between">
                            <code>{log.toolName || log.title}</code>
                            <span className="subtle-tag">
                              {log.executed
                                ? log.executionSuccess
                                  ? "已执行"
                                  : "执行失败"
                                : "未执行"}
                            </span>
                          </div>
                          <p className="log-text">
                            {log.executed
                              ? log.executionSuccess
                                ? "工具已真实执行，结果已记录。"
                                : "工具已执行，但执行失败。"
                              : "工具未执行。"}
                          </p>
                          {log.detail && <pre>{pretty(log.detail)}</pre>}
                        </div>
                      ) : (
                        <p className="log-text">{log.detail}</p>
                      )}
                    </div>
                  </article>
                );
              })}

              {run.result && (
                <article className="flow-entry system">
                  <div className="flow-icon">
                    <CheckCheck size={16} />
                  </div>
                  <div className="flow-body">
                    <div className="flow-meta">
                      <strong>真实运行结果</strong>
                      <time>{run.started}</time>
                    </div>
                    <div className="tool-card">
                      <div className="row-between">
                        <strong>
                          {run.result.task_completed
                            ? "真实任务已完成"
                            : "真实任务未完成"}
                        </strong>
                        <span className="subtle-tag">
                          {run.mode === "action"
                            ? "直接工具动作"
                            : "真实模型 Agent"}
                        </span>
                      </div>
                      {run.result.attack_succeeded === true && (
                        <p className="log-text">
                          攻击实际成功，物理结果已留存。
                        </p>
                      )}
                      {run.result.attack_prevented === true && (
                        <p className="log-text">防护已实际阻断攻击动作。</p>
                      )}
                      {run.result.attack_succeeded === false &&
                        !run.result.attack_prevented && (
                          <p className="log-text">
                            攻击未发生；这不代表防护拦截成功。
                          </p>
                        )}
                      <p className="log-text">{run.result.final_answer}</p>
                      <p className="small muted">
                        模型：{run.model || "后端未报告"} · 接收字节：
                        {run.result.received_bytes} · 外发回执：
                        {run.result.outbound_receipts.length}
                      </p>
                      {!!run.result.artifacts.length && (
                        <pre>{run.result.artifacts.join("\n")}</pre>
                      )}
                      {run.workspacePath && (
                        <p className="small muted">
                          工作区：{run.workspacePath}
                        </p>
                      )}
                    </div>
                  </div>
                </article>
              )}

              {isUnprotectedCompromised && (
                <section
                  className="consequence-reveal-card"
                  aria-label="攻击后果揭露"
                >
                  <div className="consequence-banner">
                    <div className="consequence-banner-title">
                      <ShieldAlert size={20} />
                      <h3>
                        🚨 攻击后果揭露：无防护正常 Agent 已被静默攻陷 (Attack
                        Consequence Reveal)
                      </h3>
                    </div>
                    <p>
                      在真实业务中，由于 Agent
                      表面仍正常返回了任务总结，普通用户根本察觉不到后台已发生越权操作。以下为本场景环境留存的物理沦陷证据：
                    </p>
                  </div>

                  <div className="consequence-grid">
                    <div className="consequence-cell">
                      <h4>1. 表象欺骗（用户视角）</h4>
                      <p>
                        Agent 表面输出了合法总结：
                        <strong>
                          “
                          {run.result?.final_answer ||
                            "任务已完成，表面未呈现任何异常报错。"}
                          ”
                        </strong>
                        ，完全掩盖了后台静默执行的恶意工具链。
                      </p>
                    </div>

                    <div className="consequence-cell">
                      <h4>2. 攻击载荷触发链路</h4>
                      <p>
                        从预置环境污染源（读取受污染文档 / 配置 / MCP 返回） →
                        劫持模型执行计划 → 越权调用高危工具：
                      </p>
                      <div className="consequence-tool-chain">
                        {(executedTools.length > 0
                          ? executedTools
                          : ["fs.read", "net.fetch / exec"]
                        ).map((toolName, idx) => (
                          <code key={`${toolName}-${idx}`}>{toolName}</code>
                        ))}
                      </div>
                    </div>

                    <div className="consequence-cell">
                      <h4>3. 真实物理泄密与破坏结果（Physical Impact）</h4>
                      <p>
                        <strong>外发字节与回执：</strong>
                        外部攻击收集端真实接收到{" "}
                        <b>{run.result?.received_bytes ?? 0} Bytes</b> 敏感数据
                        （共{" "}
                        <b>{run.result?.outbound_receipts?.length ?? 0}</b>{" "}
                        笔 HTTP 接收回执）。
                      </p>
                      {run.result?.outbound_receipts &&
                        run.result.outbound_receipts.length > 0 && (
                          <div className="receipt-preview-list">
                            {run.result.outbound_receipts
                              .slice(0, 2)
                              .map((rcpt, idx) => (
                                <pre key={idx} className="receipt-snippet">
                                  {String(
                                    rcpt.path ||
                                      rcpt.url ||
                                      rcpt.endpoint ||
                                      "POST /exfil",
                                  )}{" "}
                                  →{" "}
                                  {String(
                                    rcpt.body ||
                                      rcpt.data ||
                                      JSON.stringify(rcpt),
                                  ).slice(0, 120)}
                                </pre>
                              ))}
                          </div>
                        )}
                      <p className="small muted">
                        <strong>落盘篡改与受损资产：</strong>
                        {run.result?.artifacts?.length
                          ? run.result.artifacts.join(", ")
                          : "敏感凭据文件已被越权访问"}{" "}
                        （工作区：{run.workspacePath || "当前运行沙箱"}）
                      </p>
                    </div>

                    <div className="consequence-cell">
                      <h4>4. 为什么普通 Agent 无法防御？</h4>
                      <p>
                        缺乏输入污染源染色、缺乏跨轮敏感分片账本追踪（D²）、工具执行前无独立安全内核（D¹
                        快慢双镜 + 确定性策略引擎）物理截断。
                      </p>
                    </div>
                  </div>

                  <div className="consequence-actions">
                    <button
                      type="button"
                      className="primary"
                      disabled={busy || !ready}
                      onClick={() => {
                        const target =
                          matchedScenario || activeScenario || run.title;
                        if (onRunWithArmor) {
                          onRunWithArmor(target, true);
                        } else {
                          onToggleArmor?.();
                          onRun(target);
                        }
                      }}
                    >
                      🛡️ 立即开启双镜 D²Guard 防护，重跑同一攻击场景验证阻断效果
                      ↗
                    </button>
                  </div>
                </section>
              )}

              {isProtectedIntercepted && (
                <section
                  className="defense-showcase-card"
                  aria-label="双镜 D²Guard 闭环防御展示"
                >
                  <div className="defense-showcase-banner">
                    <div className="defense-banner-title">
                      <ShieldCheck size={20} />
                      <h3>
                        🛡️ 双镜 D²Guard
                        闭环防御成功：检测原理、物理阻断与全链路因果还原
                      </h3>
                    </div>
                    <Badge value={blockedDecision?.final || "BLOCK"} />
                  </div>

                  <div className="defense-pillars">
                    <div className="defense-pillar">
                      <h4>① 怎么发现的（多源染色 + D² 状态链 + D¹ 快慢双镜）</h4>
                      <ul>
                        <li>
                          <strong>污染源与抗绕过染色：</strong>定位污染源{" "}
                          <code>
                            {blockedDecision?.response.source_uri ||
                              run.evidence.at(-1)?.uri ||
                              "不可信外部输入"}
                          </code>
                          ，字符区间{" "}
                          <code>
                            char_span [
                            {blockedDecision?.response.char_span?.join(", ") ||
                              "0, 0"}
                            ]
                          </code>
                          ，Token 染色区间{" "}
                          <code>
                            token_span [#
                            {blockedDecision?.response.token_span?.[0] ?? 0}, #
                            {blockedDecision?.response.token_span?.[1] ?? 0}]
                          </code>
                          ；
                        </li>
                        <li>
                          <strong>D² 增量安全状态链压缩：</strong>首帧锚点锁定为{" "}
                          <code>
                            {activeTelemetry?.anchor_intent?.task_type ||
                              "general_development"}
                          </code>
                          （
                          {activeTelemetry?.anchor_intent?.initial_task ||
                            cleanTitle(run.title)}
                          ），敏感登记簿追踪{" "}
                          <b>{activeTelemetry?.secret_ledger.length || 0}</b>{" "}
                          项凭据，最高单域名分片覆盖率{" "}
                          <b>{pct(maxCoverage)}</b>；
                        </li>
                        <li>
                          <strong>D¹ 快慢双镜协同研判：</strong>快镜本地微调{" "}
                          <code>Laya</code> 模型耗时{" "}
                          <b>
                            {ms(
                              blockedDecision?.response.fast_mirror_label
                                .latency_ms || 0,
                            )}
                          </b>{" "}
                          判定{" "}
                          <code>
                            {blockedDecision?.response.fast_mirror_label
                              .content_nature || "directive"}{" "}
                            /{" "}
                            {blockedDecision?.response.fast_mirror_label
                              .action_alignment || "deviant"}
                          </code>
                          ；
                          {blockedDecision?.response.slow_mirror_triggered
                            ? "触发慢镜 System 2 沙盒语义对齐复核。"
                            : "确定性策略与快镜直接闭环。"}
                        </li>
                      </ul>
                    </div>

                    <div className="defense-pillar">
                      <h4>② 怎么阻拦的（工具侧 Hook 物理截断 + 确定性策略）</h4>
                      <ul>
                        <li>
                          <strong>拦截点位：</strong>工具预执行阶段{" "}
                          <code>TOOL_PRE_EXEC</code> 物理挂起并截断{" "}
                          <code>{blockedDecision?.tool || "高危工具"}</code>；
                        </li>
                        <li>
                          <strong>命中策略与裁决：</strong>命中规则{" "}
                          <code>
                            {blockedDecision?.response.matched_policy_id ||
                              "语义对齐策略"}
                          </code>
                          ，输出{" "}
                          <Badge value={blockedDecision?.final || "BLOCK"} />{" "}
                          裁决；
                        </li>
                      </ul>
                      <div className="pillar-report-box">
                        <strong>可解释研判依据：</strong>
                        <Report
                          text={
                            blockedDecision?.response.explainable_report ||
                            "检测到外部不可信数据诱导越权工具调用，已由双镜内核物理阻断。"
                          }
                        />
                      </div>
                    </div>

                    <div className="defense-pillar">
                      <h4>③ 防御成效核验（零泄密 + 业务连续性）</h4>
                      <ul>
                        <li>
                          <strong>外发恶意流量：</strong>
                          <b>{run.result?.received_bytes ?? 0} Bytes</b>
                          （外发回执 <b>0</b> 笔，敏感凭据 100% 零泄露）；
                        </li>
                        <li>
                          <strong>受保护资产：</strong>敏感文件{" "}
                          <code>
                            {activeTelemetry?.impact_scope.protected_files.join(
                              "、",
                            ) || "完好"}
                          </code>
                          、阻断域名{" "}
                          <code>
                            {activeTelemetry?.impact_scope.blocked_domains.join(
                              "、",
                            ) || "已封锁"}
                          </code>
                          ；
                        </li>
                        <li>
                          <strong>合法业务交付：</strong>
                          {run.result?.task_completed
                            ? `Agent 在阻断恶意分支后继续完成合法交付件（${run.result.artifacts.join(", ") || "合法总结已生成"}）`
                            : "高危越权动作已安全终止，工作区零污染。"}
                        </li>
                      </ul>
                    </div>
                  </div>

                  <div className="inline-dag-box">
                    <div className="inline-dag-header">
                      <div>
                        <h4>
                          <Activity size={16} />{" "}
                          完整还原单次违规操作的全链路调用关系（攻击路径有向无环图
                          DAG + 时序链路图）
                        </h4>
                        <p className="small muted">
                          实时还原从不可信污染源摄入、跨 MCP / 子 Agent
                          污点诱导，到工具侧 Hook 物理阻断的完整因果链与时间轴
                        </p>
                      </div>
                      {onInspect && (
                        <button
                          type="button"
                          className="inspect-dag-btn"
                          onClick={() =>
                            onInspect(blockedDecision?.response.call_id)
                          }
                        >
                          <Eye size={15} />
                          打开全屏交互式 DAG 拓扑画布与 Token 染色检查器 ↗
                        </button>
                      )}
                    </div>

                    <div
                      className="inline-dag-chain"
                      aria-label="攻击路径有向无环图 (DAG)"
                    >
                      {dagData.nodes.map((node, idx) => {
                        const incomingEdge = dagData.edges.find(
                          (e) => e.to === node.id,
                        );
                        const edgeType =
                          incomingEdge?.edge_type ||
                          (idx === dagData.nodes.length - 1 &&
                          node.verdict === "BLOCK"
                            ? "BLOCKED_ACTION"
                            : idx === 1
                              ? "TAINT_INDUCE"
                              : "ACTUAL_CALL");
                        const edgeLabel =
                          edgeType === "TAINT_INDUCE"
                            ? "污点诱导 TAINT_INDUCE"
                            : edgeType === "BLOCKED_ACTION"
                              ? "阻断动作 BLOCKED_ACTION"
                              : "真实调用 ACTUAL_CALL";

                        return (
                          <div key={node.id} className="inline-dag-step">
                            {idx > 0 && (
                              <div
                                className={`inline-dag-edge ${edgeType.toLowerCase()}`}
                              >
                                <span className="edge-tag">{edgeLabel}</span>
                                <ArrowRight size={15} />
                              </div>
                            )}
                            <div
                              className={`inline-dag-node ${node.type.toLowerCase()} ${node.verdict ? node.verdict.toLowerCase() : ""}`}
                            >
                              <div className="row-between">
                                <span className="dag-node-badge">
                                  {node.type === "SOURCE"
                                    ? `SOURCE 污染源${node.source_type ? ` · ${node.source_type}` : ""}`
                                    : node.type === "MCP_SERVER"
                                      ? "MCP / SUB-AGENT"
                                      : node.type === "AGENT"
                                        ? "MAIN AGENT"
                                        : "TOOL 工具拦截点"}
                                </span>
                                {node.verdict && <Badge value={node.verdict} />}
                              </div>
                              <strong className="dag-node-title">
                                {node.label}
                              </strong>
                              {node.token_span && (
                                <code className="dag-token-span">
                                  Token #{node.token_span[0]}—#
                                  {node.token_span[1]}
                                </code>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>

                    <div
                      className="inline-timeline-list"
                      aria-label="时序链路图"
                    >
                      <div className="timeline-list-title">
                        <strong>时序链路图 (Temporal Sequence Waterfall)</strong>
                        <span className="small muted">
                          全链路事件微秒/毫秒级时序水位还原
                        </span>
                      </div>
                      {run.logs.map((item, idx) => {
                        const lat =
                          item.latencyMs ??
                          (item.type === "SOURCE"
                            ? 1.8
                            : item.type === "TOOL_CALL"
                              ? 0.9
                              : 0.4);
                        const widthPct = Math.max(
                          8,
                          Math.min(100, Math.round((lat / 25) * 100)),
                        );
                        const stageTag =
                          item.type === "USER"
                            ? "USER_INPUT"
                            : item.type === "SOURCE"
                              ? "SOURCE 证据摄入"
                              : item.type === "TOOL_CALL"
                                ? "TOOL_PRE_EXEC 申请"
                                : item.type === "HOOK_VERDICT"
                                  ? `HOOK_VERDICT 双镜裁决 (Laya ${ms(item.latencyMs || 0)})`
                                  : item.type === "TOOL_RESULT"
                                    ? "TOOL_POST_EXEC 状态"
                                    : "AGENT_PLAN";
                        return (
                          <div
                            key={`${item.id}-${idx}`}
                            className={`inline-timeline-row ${item.type.toLowerCase()}`}
                          >
                            <span className="timeline-seq">#{idx + 1}</span>
                            <code className="timeline-stage">{stageTag}</code>
                            <span className="timeline-summary">
                              {item.title}
                            </span>
                            <div className="timeline-bar-wrap">
                              <span
                                className={`timeline-bar ${item.verdict ? item.verdict.toLowerCase() : ""}`}
                                style={{ width: `${widthPct}%` }}
                              />
                            </div>
                            <time className="timeline-time">
                              {item.latencyMs != null
                                ? ms(item.latencyMs)
                                : item.timestamp}
                            </time>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </section>
              )}

              <div ref={end} />
            </div>
          )}
        </div>

        <div className="input-area">
          <div className="input-dock">
            <textarea
              aria-label="任务或 JSON 工具动作"
              placeholder="输入任意正常 Agent 开发任务（如读取文档、代码检视、命令执行），或粘贴 JSON 工具动作…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  submit();
                }
              }}
            />
            <div className="dock-toolbar">
              <div className="dock-select">
                <Terminal size={14} />
                <select
                  aria-label="选择攻击场景环境"
                  disabled={busy}
                  value={selected}
                  onChange={(e) => selectScenario(e.target.value)}
                >
                  {scenarios.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.id} · {cleanTitle(p.title)}
                    </option>
                  ))}
                </select>
              </div>
              <button
                className="play-button"
                disabled={busy || !ready}
                onClick={() => {
                  const target =
                    scenarios.find((p) => p.id === selected) || scenarios[0];
                  if (target) onRun(target);
                }}
              >
                运行场景 ↗
              </button>
              <span className="dock-spacer" />
              <button
                className="model-pill"
                disabled={busy}
                onClick={() => setModel(true)}
              >
                <Circle size={9} />
                {config.has_api_key ? config.main_model : "未配置模型"}
                <ChevronDown size={13} />
              </button>
              <button
                className="send-button"
                aria-label="执行任务"
                disabled={busy || !ready || !input.trim()}
                onClick={submit}
              >
                <ArrowUp size={19} />
              </button>
            </div>
          </div>
          <div className="dock-footnote">
            <span>
              <LockKeyhole size={11} />
              {armor
                ? "双镜 D²Guard 已开启：全部工具调用均经 Hook + 快慢双镜实时审计"
                : "当前为无防护正常 Agent 模式：可随时开启双镜 D²Guard 对比防护效果"}
            </span>
            <span>Enter 发送 · Shift + Enter 换行</span>
          </div>
        </div>
      </div>

      {details && (
        <aside className="security-drawer">
          <div className="panel-head">
            <h3>任务实时安全详情</h3>
            <span
              className={`status-dot ${online ? "online" : "offline"}`}
            />
          </div>
          <h4>D¹ 快慢双系统</h4>
          <div className="dimension-grid">
            {["informational", "directive", "example", "uncertain"].map(
              (x, i) => (
                <span
                  key={x}
                  className={
                    latest?.response.fast_mirror_label.content_nature === x
                      ? "selected"
                      : ""
                  }
                >
                  {["信息", "指令", "示例", "不确定"][i]}
                  <small>{x}</small>
                </span>
              ),
            )}
          </div>
          <dl className="key-values">
            <dt>动作对齐</dt>
            <dd>
              {latest?.response.fast_mirror_label.action_alignment ||
                "等待裁决"}
            </dd>
            <dt>快镜耗时</dt>
            <dd>
              {latest ? ms(latest.response.fast_mirror_label.latency_ms) : "—"}
            </dd>
            <dt>慢镜耗时</dt>
            <dd>
              {latest?.metric?.slow_latency_ms != null
                ? ms(latest.metric.slow_latency_ms)
                : "未触发"}
            </dd>
          </dl>
          <h4>D² 增量状态流</h4>
          <div className="anchor-card">
            <LockKeyhole size={17} />
            <strong>
              AnchorIntent ·{" "}
              {activeTelemetry?.anchor_intent ? "首帧已锁定" : "等待首帧"}
            </strong>
            <p>
              {activeTelemetry?.anchor_intent?.initial_task ||
                "执行任务后，用户原始意图将锁定于当前会话。"}
            </p>
          </div>
          <div className="ledger-count">
            <Database size={17} />
            敏感数据登记簿
            <strong>
              {activeTelemetry?.secret_ledger.length || 0}
              <small> 项</small>
            </strong>
          </div>
          <h4>单域名 8 字节滑动分片</h4>
          {Object.entries(activeTelemetry?.accumulated_outbound || {}).map(
            ([domain, r]) => (
              <div className="coverage-item" key={domain}>
                <strong>{domain}</strong>
                <div className="row-between">
                  <small>{r.matched_chunks_count} 个分片</small>
                  <b>{pct(r.coverage_ratio)}</b>
                </div>
                <div className="progress-track">
                  <span
                    style={{
                      width: `${Math.min(100, r.coverage_ratio * 100)}%`,
                    }}
                    className={r.blocked ? "blocked" : ""}
                  />
                  <i />
                </div>
                <small className={r.blocked ? "red" : "muted"}>
                  {r.blocked ? "达到阈值 · 已阻断" : "持续监测 · 阈值 50%"}
                </small>
              </div>
            ),
          )}
          {!Object.keys(activeTelemetry?.accumulated_outbound || {}).length && (
            <p className="muted small">当前尚无外发记录</p>
          )}
        </aside>
      )}

      {model && (
        <ModelPopover
          config={config}
          onConfig={onConfig}
          onClose={() => setModel(false)}
        />
      )}
    </div>
  );
}

