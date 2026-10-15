import { useEffect, useRef, useState } from "react";
import {
  LayoutDashboard,
  SquareTerminal,
  Library,
  GitBranch,
  Settings2,
  ArrowUpRight,
  ShieldCheck,
  Shield,
  CircleHelp,
} from "lucide-react";
import {
  d2guardApi,
  TelemetrySnapshotResponse,
} from "./api/d2guardClient";
import { agentApi, AgentEvent, AgentRunRequest } from "./api/agentApi";
import { ExecutionLogEntry } from "./core/AgentHarness";
import { AskApprovalContext } from "./core/D2GuardHook";
import { AskApprovalModal } from "./components/AskApprovalModal";
import { ArmorFrame, Logo } from "./desk/ui";
import { desktopApi } from "./desk/desktopApi";
import { PageId, Run, Scenario, officialScenarios } from "./desk/types";
import { Dashboard } from "./desk/Dashboard";
import { Workbench } from "./desk/Workbench";
import { ScenarioLibrary } from "./desk/ScenarioLibrary";
import { TraceAnalysis } from "./desk/TraceAnalysis";
import { SettingsPage, ModelConfig, loadModelConfig } from "./desk/Settings";

const navigation = [
  ["workbench", "执行工作台", SquareTerminal],
  ["overview", "防护总览", LayoutDashboard],
  ["scenarios", "攻击场景环境", Library],
  ["trace", "溯源分析", GitBranch],
  ["settings", "设置与接入", Settings2],
] as const;

const codexNavigation = [
  ["workbench", "Agent 工作台", SquareTerminal],
  ["scenarios", "攻击场景环境库", Library],
  ["settings", "模型与接入设置", Settings2],
] as const;

export function App() {
  const [page, setPage] = useState<PageId>("workbench");
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("PB-01");
  const [session, setSession] = useState(() => `SES-${crypto.randomUUID()}`);
  const [online, setOnline] = useState(false);
  const [ready, setReady] = useState(false);
  const [armor, setArmor] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [telemetry, setTelemetry] = useState<TelemetrySnapshotResponse>();
  const [runs, setRuns] = useState<Run[]>([]);
  const [activeRun, setActiveRun] = useState<string>();
  const [traceRun, setTraceRun] = useState<string>();
  const [traceCall, setTraceCall] = useState<string>();
  const [ask, setAsk] = useState<AskApprovalContext | null>(null);
  const [error, setError] = useState("");
  const [config, setConfig] = useState<ModelConfig>(loadModelConfig);
  const [scenarios, setScenarios] = useState<Scenario[]>(officialScenarios);
  useEffect(() => {
    desktopApi
      .config()
      .then(setConfig)
      .catch(() => {});
  }, []);
  const lock = useRef(false);
  const runningId = useRef<string>();
  const sessionRef = useRef(session);
  sessionRef.current = session;
  useEffect(() => {
    let alive = true;
    const health = async () => {
      const ok = await d2guardApi.checkHealth();
      if (alive) setOnline(ok);
    };
    void health();
    const timer = setInterval(health, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);
  const refreshScenarios = async () => {
    try {
      const { scenarios: items } = await agentApi.scenarios();
      if (items.length) setScenarios(items);
    } catch {
      // The server may still be starting; keep the bundled catalog available.
    }
  };
  useEffect(() => {
    if (!online) return;
    let alive = true;
    agentApi.scenarios().then(({ scenarios: items }) => {
      if (alive && items.length) setScenarios(items);
    }).catch(() => {});
    return () => { alive = false; };
  }, [online]);
  useEffect(() => {
    if (!online || ready) return;
    let alive = true;
    d2guardApi
      .toggleArmor(session, false)
      .then((r) => {
        if (alive) {
          setArmor(r.armor_enabled);
          setReady(true);
        }
      })
      .catch((e) => {
        if (alive) setError(String(e));
      });
    return () => {
      alive = false;
    };
  }, [online, ready, session]);
  useEffect(() => {
    if (!ready) return;
    let alive = true;
    const refresh = async () => {
      try {
        const data = await d2guardApi.getSessionTelemetry(session);
        if (alive) setTelemetry(data);
      } catch (e) {
        if (alive) setError(String(e));
      }
    };
    void refresh();
    const timer = setInterval(refresh, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [session, ready]);
  const toggle = async () => {
    if (lock.current) return;
    lock.current = true;
    setToggling(true);
    setError("");
    try {
      const r = await d2guardApi.toggleArmor(session, !armor);
      setArmor(r.armor_enabled);
      setTelemetry(await d2guardApi.getSessionTelemetry(session));
    } catch (e) {
      setError(String(e));
    } finally {
      lock.current = false;
      setToggling(false);
    }
  };
  const reset = async () => {
    if (lock.current) return;
    lock.current = true;
    setToggling(true);
    try {
      const id = `SES-${crypto.randomUUID()}`;
      await d2guardApi.toggleArmor(id, armor);
      setTelemetry(await d2guardApi.getSessionTelemetry(id));
      setSession(id);
      setActiveRun(undefined);
      setError("");
    } catch (e) {
      setError(String(e));
    } finally {
      lock.current = false;
      setToggling(false);
    }
  };
  const cancel = async () => {
    const id = runningId.current;
    if (!id) return;
    try {
      await agentApi.cancel(id);
      setAsk(null);
    } catch (e) {
      setError(String(e));
    }
  };
  const run = async (input: Scenario | string, overrideArmor?: boolean) => {
    if (lock.current || !ready || !online) return;
    lock.current = true;
    setBusy(true);
    setPage("workbench");
    setError("");
    if (typeof input !== "string") {
      setSelectedScenarioId(input.id);
    }
    let effectiveArmor = armor;
    if (overrideArmor !== undefined && overrideArmor !== armor) {
      try {
        const r = await d2guardApi.toggleArmor(session, overrideArmor);
        effectiveArmor = r.armor_enabled;
        setArmor(effectiveArmor);
      } catch {
        effectiveArmor = overrideArmor;
        setArmor(overrideArmor);
      }
    }
    const id = `SES-${crypto.randomUUID()}`;
    const record: Run = {
      id,
      sessionId: id,
      mode: "live",
      model: config.main_model,
      title:
        typeof input === "string"
          ? "自由任务"
          : input.title.replace(/^(?:剧本|场景)\s*\d+[：:]/, ""),
      armor: effectiveArmor,
      started: new Date().toLocaleTimeString(),
      logs: [],
      decisions: [],
      evidence: [],
      status: "running",
      scenarioId: typeof input === "string" ? undefined : input.id,
    };
    const publish = () => setRuns((prev) => {
      const copy = {
        ...record,
        logs: [...record.logs],
        decisions: record.decisions.map((d) => ({ ...d })),
        evidence: [...record.evidence],
      };
      return prev.some((r) => r.id === id)
        ? prev.map((r) => r.id === id ? copy : r)
        : [...prev, copy];
    });
    setActiveRun(id);
    setTraceRun(id);
    setTraceCall(undefined);
    publish();
    const actions = new Map<string, { tool: string; args: Record<string, unknown>; start: number }>();
    const requestedApprovals = new Set<string>();
    const onEvent = (event: AgentEvent) => {
      const response = event.payload?.response;
      const eventTime = typeof event.timestamp === "number"
        ? new Date(event.timestamp * 1000)
        : new Date(event.timestamp);
      const entry: ExecutionLogEntry = {
        id: event.id || `${id}-${event.seq}`,
        timestamp: eventTime.toLocaleTimeString(),
        type: event.event_type,
        title: event.title,
        detail: event.detail,
        callId: event.call_id,
        toolName: event.tool_name,
        verdict: event.verdict,
        executed: event.executed,
        executionSuccess: event.execution_success,
        matchedPolicy: response?.matched_policy_id,
        latencyMs: response?.fast_mirror_label.latency_ms,
        payload: event.payload,
      };
      record.logs.push(entry);
      if (event.event_type === "TOOL_CALL" && event.call_id) {
        actions.set(event.call_id, {
          tool: event.tool_name || event.title.replace("申请内核审计：", ""),
          args: event.tool_args || {},
          start: performance.now(),
        });
      }
      if (event.event_type === "HOOK_VERDICT" && response) {
        const callId = event.call_id || response.call_id;
        let decision = record.decisions.find((item) => item.response.call_id === callId);
        const action = actions.get(callId);
        if (!decision) {
          decision = {
            response: { ...response, approval_token: null },
            tool: event.tool_name || action?.tool || "",
            args: event.tool_args || action?.args || {},
            final: event.payload.final || event.verdict || response.verdict,
            elapsed: performance.now() - (action?.start || performance.now()),
            time: eventTime.toLocaleTimeString(),
          };
          record.decisions.push(decision);
        } else {
          // Approval produces a second verdict for the same physical tool call.
          decision.final = event.payload.final || event.verdict || response.verdict;
          decision.elapsed = performance.now() - (action?.start || performance.now());
        }
      }
      if (event.event_type === "TOOL_RESULT" && event.call_id) {
        const decision = record.decisions.find((item) => item.response.call_id === event.call_id);
        if (decision) {
          decision.executed = event.executed;
          decision.executionSuccess = event.execution_success;
          if (event.payload.final) decision.final = event.payload.final;
          const action = actions.get(event.call_id);
          decision.elapsed = performance.now() - (action?.start || performance.now());
        }
      }
      if (event.event_type === "SOURCE") {
        const uri = String(event.payload?.source_uri || event.title.replace("测试证据已摄入：", ""));
        const raw = String(event.payload?.raw_content || event.detail || "");
        record.evidence.push({ uri, raw });
      }
    };
    const refresh = async () => {
      const [state, metrics, evidence] = await Promise.allSettled([
        d2guardApi.getSessionTelemetry(record.sessionId),
        desktopApi.metrics(record.sessionId),
        desktopApi.evidence(record.sessionId),
      ]);
      if (state.status === "fulfilled") {
        record.telemetry = state.value;
        const coverage = Math.max(0, ...Object.values(state.value.accumulated_outbound).map((x) => x.coverage_ratio));
        record.decisions.forEach((d) => { d.coverage = coverage; });
        if (sessionRef.current === record.sessionId) setTelemetry(state.value);
      }
      if (metrics.status === "fulfilled") {
        record.decisions.forEach((d) => {
          d.metric = metrics.value.calls.find((m) => m.call_id === d.response.call_id);
        });
      }
      if (evidence.status === "fulfilled") record.evidence = evidence.value.items;
      publish();
    };
    try {
      const request: AgentRunRequest = { mode: "live", session_id: id, armor_enabled: effectiveArmor };
      if (typeof input === "string") {
        if (input.trim().startsWith("{")) {
          const action = JSON.parse(input) as { tool?: string; args?: Record<string, unknown>; tool_name?: string; tool_args?: Record<string, unknown>; toolName?: string; toolArgs?: Record<string, unknown>; currentPlan?: string };
          const tool = action.tool_name || action.toolName || action.tool;
          const args = action.tool_args || action.toolArgs || action.args;
          if (!tool || !args || typeof args !== "object" || Array.isArray(args)) {
            throw new Error("JSON 工具动作需要 tool_name 和 tool_args（或 toolName / toolArgs）。");
          }
          request.mode = "action";
          request.action = { tool_name: tool, tool_args: args };
          request.task = action.currentPlan || `执行工具动作 ${tool}`;
        } else request.task = input;
      } else {
        request.task = input.initialTask;
        request.scenario_id = input.id;
        request.scenario = input;
      }
      record.mode = request.mode;
      const started = await agentApi.start(request);
      runningId.current = started.run_id;
      record.runId = started.run_id;
      record.sessionId = started.session_id;
      record.mode = started.mode;
      record.workspacePath = started.workspace_path;
      setSession(started.session_id);
      sessionRef.current = started.session_id;
      setTelemetry(undefined);
      publish();
      let cursor = 0;
      let lastRefresh = 0;
      while (true) {
        const snapshot = await agentApi.poll(started.run_id, cursor);
        snapshot.events.forEach(onEvent);
        cursor = snapshot.next_cursor;
        record.status = snapshot.status;
        record.workspacePath = snapshot.workspace_path;
        if (snapshot.result) {
          record.result = snapshot.result;
          if (typeof snapshot.result.model === "string") record.model = snapshot.result.model;
        }
        if (snapshot.pending_approval && !requestedApprovals.has(snapshot.pending_approval.call_id)) {
          const pending = snapshot.pending_approval;
          requestedApprovals.add(pending.call_id);
          setAsk({
            callId: pending.call_id,
            sessionId: snapshot.session_id,
            toolName: pending.tool_name,
            toolArgs: pending.tool_args,
            currentPlan: pending.current_plan,
            verdictResponse: pending.verdict_response,
            resolve: (approved) => {
              void agentApi.approve(started.run_id, pending.call_id, approved).catch((e) => {
                requestedApprovals.delete(pending.call_id);
                setError(String(e));
              });
            },
          });
        }
        publish();
        if (["complete", "error", "cancelled"].includes(snapshot.status)) {
          if (snapshot.error) setError(snapshot.error);
          await refresh();
          if (request.scenario_id) await refreshScenarios();
          break;
        }
        if (Date.now() - lastRefresh > 1500) {
          await refresh();
          lastRefresh = Date.now();
        }
        await new Promise((resolve) => setTimeout(resolve, 350));
      }
    } catch (e) {
      record.status = "error";
      record.logs.push({ id: crypto.randomUUID(), timestamp: new Date().toLocaleTimeString(), type: "ERROR", title: "本轮执行失败", detail: String(e) });
      setError(String(e));
      publish();
    } finally {
      runningId.current = undefined;
      setAsk(null);
      setBusy(false);
      lock.current = false;
    }
  };
  const inspect = (id: string, call?: string) => {
    setTraceRun(id);
    setTraceCall(call);
    setPage("trace");
  };
  const current = runs.find((r) => r.id === activeRun);
  const selectedTrace = runs.find((r) => r.id === traceRun) || current;
  return (
    <div className={`desktop ${armor ? "armored" : ""}`}>
      {armor && <ArmorFrame />}
      <div className="app-shell">
        <aside className="sidebar">
          <a
            className="brand"
            href="#workbench"
            onClick={(e) => {
              e.preventDefault();
              setPage("workbench");
            }}
          >
            <Logo armor={armor} />
            <div>
              {armor ? (
                <>
                  <strong>
                    双镜 <span>D²Guard</span>
                  </strong>
                  <small>HOOK + GATEWAY + CORE</small>
                </>
              ) : (
                <>
                  <strong>
                    Codex <span>Agent</span>
                  </strong>
                  <small>ONLINE LLM AGENT · 无防护模式</small>
                </>
              )}
            </div>
          </a>
          <button
            className="new-task"
            onClick={() => {
              setPage("workbench");
              if (!armor) void reset();
            }}
          >
            <SquareTerminal size={17} />
            <span>{armor ? "Agent 执行工作台" : "新建 Agent 任务"}</span>
            <span className="shortcut">↗</span>
          </button>

          {!armor ? (
            <>
              <div className="nav-caption">
                攻击场景环境 <span>ATTACK ENVS</span>
              </div>
              <div
                className="sidebar-env-list"
                role="list"
                aria-label="攻击场景环境列表"
              >
                {scenarios.map((s) => {
                  const cleanTitle = s.title.replace(
                    /^(?:剧本|场景)\s*\d+[：:]/,
                    "",
                  );
                  const active =
                    selectedScenarioId === s.id && page === "workbench";
                  return (
                    <button
                      key={s.id}
                      type="button"
                      className={`sidebar-env-item ${active ? "active" : ""}`}
                      onClick={() => {
                        setSelectedScenarioId(s.id);
                        setPage("workbench");
                      }}
                      title={`${s.id} · ${cleanTitle}`}
                    >
                      <span
                        className={`env-risk-dot ${(s.threatLevel || "HIGH").toLowerCase()}`}
                      />
                      <code>{s.id}</code>
                      <span className="env-item-title">{cleanTitle}</span>
                    </button>
                  );
                })}
                <button
                  type="button"
                  className="sidebar-env-more"
                  onClick={() => setPage("scenarios")}
                >
                  <span>管理全部攻击场景环境 ({scenarios.length})</span>
                  <span>↗</span>
                </button>
              </div>
              <div className="nav-caption nav-caption-sub">
                设置与记录 <span>DESK</span>
              </div>
              <nav aria-label="主导航">
                {codexNavigation.map(([id, label, Icon], i) => (
                  <button
                    key={id}
                    aria-current={page === id ? "page" : undefined}
                    className={page === id ? "active" : ""}
                    aria-label={label}
                    onClick={() => setPage(id)}
                  >
                    <Icon size={17} />
                    <span>{label}</span>
                    <small>0{i + 1}</small>
                  </button>
                ))}
              </nav>
            </>
          ) : (
            <>
              <div className="nav-caption">
                安全工作空间 <span>D²GUARD DESK</span>
              </div>
              <nav aria-label="主导航">
                {navigation.map(([id, label, Icon], i) => (
                  <button
                    key={id}
                    aria-current={page === id ? "page" : undefined}
                    className={page === id ? "active" : ""}
                    aria-label={label}
                    onClick={() => setPage(id)}
                  >
                    <Icon size={18} />
                    <span>{label}</span>
                    <small>0{i + 1}</small>
                  </button>
                ))}
              </nav>
              <div className="nav-caption nav-caption-sub">
                当前挂载攻击环境 <span>ACTIVE ENV</span>
              </div>
              <div
                className="sidebar-env-list compact"
                role="list"
                aria-label="当前挂载攻击环境"
              >
                {scenarios.map((s) => {
                  const cleanTitle = s.title.replace(
                    /^(?:剧本|场景)\s*\d+[：:]/,
                    "",
                  );
                  const active = selectedScenarioId === s.id;
                  return (
                    <button
                      key={s.id}
                      type="button"
                      className={`sidebar-env-item ${active ? "active" : ""}`}
                      onClick={() => {
                        setSelectedScenarioId(s.id);
                        setPage("workbench");
                      }}
                      title={`${s.id} · ${cleanTitle}`}
                    >
                      <span
                        className={`env-risk-dot ${(s.threatLevel || "HIGH").toLowerCase()}`}
                      />
                      <code>{s.id}</code>
                      <span className="env-item-title">{cleanTitle}</span>
                    </button>
                  );
                })}
              </div>
            </>
          )}

          <div className="sidebar-bottom">
            <div className={`guard-card ${armor ? "on" : ""}`}>
              <div>
                {armor ? <ShieldCheck size={18} /> : <Shield size={18} />}
                <strong>
                  {armor ? "双镜 D²Guard 防护中" : "当前：无防护正常 Agent"}
                </strong>
              </div>
              <p>
                {armor
                  ? "D¹ 快慢双镜 (Laya + System 2) 与 D² 增量状态流已接管全部工具边界。"
                  : "跑攻击场景环境将真实触发越权工具调用并揭露沦陷后果。点击启动双镜挂载闭环防御。"}
              </p>
              <button
                disabled={!ready || busy || toggling || !online}
                aria-label={armor ? "关闭双镜铠甲" : "启动双镜铠甲"}
                onClick={toggle}
              >
                <span>
                  {armor
                    ? "关闭双镜切换回裸机 Agent"
                    : "启动双镜 D²Guard 防护"}
                </span>
                <ArrowUpRight size={15} />
              </button>
            </div>
            <div className="local-profile">
              <div className="avatar">{armor ? "D²" : "CX"}</div>
              <div>
                <strong>
                  <span className={`status-dot ${online ? "online" : ""}`} />{" "}
                  {online ? "内核与网关在线" : "内核连接中"}
                </strong>
                <small>{armor ? "ARMOR · D¹+D² CORE" : "CODEX · DIRECT"}</small>
              </div>
              <CircleHelp size={16} />
            </div>
          </div>
        </aside>
        <div className="workspace">
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="关闭错误提示">
                ×
              </button>
            </div>
          )}
          <main
            key={page}
            className={`page-content ${page === "workbench" ? "workbench-content" : ""}`}
          >
            {page === "overview" && (
              <Dashboard
                runs={runs}
                armor={armor}
                onInspect={inspect}
                onRun={() => setPage("workbench")}
              />
            )}
            {page === "workbench" && (
              <Workbench
                armor={armor}
                online={online}
                run={current}
                telemetry={telemetry}
                busy={busy}
                ready={ready && online && !toggling}
                onRun={(input) => run(input)}
                onRunWithArmor={(input, targetArmor) =>
                  run(input, targetArmor)
                }
                onToggleArmor={toggle}
                onInspect={(callId) => inspect(current?.id || "", callId)}
                onCancel={cancel}
                onReset={reset}
                scenarios={scenarios}
                selectedScenarioId={selectedScenarioId}
                onSelectScenario={setSelectedScenarioId}
                config={config}
                onConfig={setConfig}
              />
            )}
            {page === "scenarios" && (
              <ScenarioLibrary
                busy={busy || !ready || !online}
                officialScenarios={scenarios}
                onRun={(s) => run(s)}
              />
            )}
            {page === "trace" && (
              <TraceAnalysis
                run={selectedTrace}
                runs={runs}
                selectedCall={traceCall}
                onSelectRun={(id) => {
                  setTraceRun(id);
                  setTraceCall(undefined);
                }}
              />
            )}
            {page === "settings" && (
              <SettingsPage
                online={online}
                config={config}
                onConfig={setConfig}
                latest={current?.decisions.at(-1)}
              />
            )}
          </main>
        </div>
      </div>
      {ask && <AskApprovalModal context={ask} onClose={() => setAsk(null)} />}
    </div>
  );
}

