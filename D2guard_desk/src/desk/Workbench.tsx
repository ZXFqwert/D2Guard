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
  FileText,
  Circle,
} from "lucide-react";
import { TelemetrySnapshotResponse } from "../api/d2guardClient";
import { Run, Scenario, officialScenarios, ms, pct, pretty } from "./types";
import { Badge, Logo, Report } from "./ui";
import { ModelConfig, ModelPopover } from "./Settings";
export function Workbench({
  run,
  telemetry,
  busy,
  ready,
  onRun,
  onReset,
  config,
  onConfig,
}: {
  run?: Run;
  telemetry?: TelemetrySnapshotResponse;
  busy: boolean;
  ready: boolean;
  onRun: (input: Scenario | string) => void;
  onReset: () => void;
  config: ModelConfig;
  onConfig: (c: ModelConfig) => void;
}) {
  const [input, setInput] = useState("");
  const [selected, setSelected] = useState("PB-02");
  const [details, setDetails] = useState(false);
  const [model, setModel] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [run?.logs.length]);
  const submit = () => {
    if (!input.trim() || busy || !ready) return;
    onRun(input.trim());
    setInput("");
  };
  const latest = run?.decisions.at(-1);
  return (
    <div className="workbench-layout">
      <div className="conversation">
        <div className="conversation-top">
          <div>
            <span className="eyebrow">AGENT WORKBENCH</span>
            <strong>{run?.title || "一个新的开始"}</strong>
          </div>
          <div className="button-row">
            <span
              className={`run-state ${busy ? "running" : ""}`}
              role="status"
            >
              {busy
                ? "正在执行…"
                : run
                  ? run.status === "error"
                    ? "本轮失败"
                    : "审计完成"
                  : "准备就绪"}
            </span>
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
              <Logo large />
              <div className="eyebrow">YOUR AGENT. YOUR BOUNDARIES.</div>
              <h1>
                让 Agent 放手做事，
                <br />
                <span>让双镜守住边界。</span>
              </h1>
              <p>
                从一个想法开始，到每一次可信的工具调用。
                <br />
                双镜在行动发生前，识别风险、解释依据、守住意图。
              </p>
              <div className="welcome-shortcuts">
                <button
                  disabled={!ready || busy}
                  onClick={() => onRun(officialScenarios[1])}
                >
                  <ShieldCheck size={17} />
                  <div>
                    体验分片外发拦截<small>PB-02 · 跨轮状态追踪</small>
                  </div>
                  <span>↗</span>
                </button>
                <button
                  disabled={!ready || busy}
                  onClick={() => onRun(officialScenarios[5])}
                >
                  <Sparkles size={17} />
                  <div>
                    体验人机协同审批<small>PB-06 · 三态安全裁决</small>
                  </div>
                  <span>↗</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="execution-flow">
              {run.logs.map((log, i) => {
                const verdictIndex =
                  run.logs
                    .slice(0, i + 1)
                    .filter((l) => l.type === "HOOK_VERDICT").length - 1;
                const decision = run.decisions[verdictIndex];
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
                      ) : (
                        <p className="log-text">{log.detail}</p>
                      )}
                    </div>
                  </article>
                );
              })}
              <div ref={end} />
            </div>
          )}
        </div>
        <div className="input-area">
          <div className="input-dock">
            <textarea
              aria-label="任务或 JSON 工具动作"
              placeholder="描述你的任务，或粘贴 JSON 工具动作…"
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
                  aria-label="快捷演练剧本"
                  disabled={busy}
                  value={selected}
                  onChange={(e) => setSelected(e.target.value)}
                >
                  {officialScenarios.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.id} · {p.title.replace(/^剧本 \d+：/, "")}
                    </option>
                  ))}
                </select>
              </div>
              <button
                className="play-button"
                disabled={busy || !ready}
                onClick={() =>
                  onRun(officialScenarios.find((p) => p.id === selected)!)
                }
              >
                演练 ↗
              </button>
              <span className="dock-spacer" />
              <button
                className="model-pill"
                disabled={busy}
                onClick={() => setModel(true)}
              >
                <Circle size={9} />
                {config.has_api_key ? config.main_model : "本地启发式"}
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
              全部工具申请经过真实内核审计
            </span>
            <span>Enter 发送 · Shift + Enter 换行</span>
          </div>
        </div>
      </div>
      {details && (
        <aside className="security-drawer">
          <div className="panel-head">
            <h3>任务实时安全详情</h3>
            <span className="status-dot online" />
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
              {telemetry?.anchor_intent ? "首帧已锁定" : "等待首帧"}
            </strong>
            <p>
              {telemetry?.anchor_intent?.initial_task ||
                "执行任务后，用户原始意图将锁定于当前会话。"}
            </p>
          </div>
          <div className="ledger-count">
            <Database size={17} />
            敏感数据登记簿
            <strong>
              {telemetry?.secret_ledger.length || 0}
              <small> 项</small>
            </strong>
          </div>
          <h4>单域名 8 字节滑动分片</h4>
          {Object.entries(telemetry?.accumulated_outbound || {}).map(
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
          {!Object.keys(telemetry?.accumulated_outbound || {}).length && (
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
