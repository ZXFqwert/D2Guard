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
  BASE_URL,
  d2guardApi,
  TelemetrySnapshotResponse,
  ExtractedSummary,
} from "./api/d2guardClient";
import { AgentHarness, ExecutionLogEntry } from "./core/AgentHarness";
import { AskApprovalContext, D2GuardHook } from "./core/D2GuardHook";
import { AskApprovalModal } from "./components/AskApprovalModal";
import { ArmorFrame, Logo } from "./desk/ui";
import { desktopApi } from "./desk/desktopApi";
import { PageId, Run, Scenario, Decision } from "./desk/types";
import { Dashboard } from "./desk/Dashboard";
import { Workbench } from "./desk/Workbench";
import { ScenarioLibrary } from "./desk/ScenarioLibrary";
import { TraceAnalysis } from "./desk/TraceAnalysis";
import { SettingsPage, ModelConfig, loadModelConfig } from "./desk/Settings";

const navigation = [
  ["overview", "防护总览", LayoutDashboard],
  ["workbench", "执行工作台", SquareTerminal],
  ["scenarios", "场景库管理", Library],
  ["trace", "溯源分析", GitBranch],
  ["settings", "设置与接入", Settings2],
] as const;
export function App() {
  const [page, setPage] = useState<PageId>("overview");
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
  useEffect(() => {
    desktopApi
      .config()
      .then(setConfig)
      .catch(() => {});
  }, []);
  const lock = useRef(false);
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
  const run = async (input: Scenario | string) => {
    if (lock.current || !ready || !online) return;
    lock.current = true;
    setBusy(true);
    setPage("workbench");
    setError("");
    const id = `SES-${crypto.randomUUID()}`;
    const record: Run = {
      id,
      title:
        typeof input === "string"
          ? "自由任务"
          : input.title.replace(/^剧本 \d+：/, ""),
      armor,
      started: new Date().toLocaleTimeString(),
      logs: [],
      decisions: [],
      evidence: [],
      status: "running",
      scenarioId: typeof input === "string" ? undefined : input.id,
    };
    const publish = () =>
      setRuns((prev) => {
        const copy = {
          ...record,
          logs: [...record.logs],
          decisions: record.decisions.map((d) => ({ ...d })),
          evidence: [...record.evidence],
        };
        return prev.some((r) => r.id === id)
          ? prev.map((r) => (r.id === id ? copy : r))
          : [...prev, copy];
      });
    setActiveRun(id);
    setTraceRun(id);
    setTraceCall(undefined);
    publish();
    let action:
      | { tool: string; args: Record<string, unknown>; start: number }
      | undefined;
    let decision: Decision | undefined;
    const refresh = async () => {
      const state = await d2guardApi.getSessionTelemetry(id);
      record.telemetry = state;
      if (decision)
        decision.coverage = Math.max(
          0,
          ...Object.values(state.accumulated_outbound).map(
            (x) => x.coverage_ratio,
          ),
        );
      if (sessionRef.current === id) setTelemetry(state);
      publish();
    };
    const pendingRefreshes: Promise<void>[] = [];
    const onLog = (entry: ExecutionLogEntry) => {
      record.logs.push(entry);
      if (entry.type === "TOOL_CALL") {
        action = {
          tool: entry.title.replace("申请内核审计：", ""),
          args: JSON.parse(entry.detail || "{}"),
          start: performance.now(),
        };
      }
      if (entry.type === "SOURCE" && typeof input !== "string") {
        const uri = entry.title.replace("测试证据已摄入：", "");
        const step = input.steps.find(
          (s) =>
            s.actionType === "INGEST" &&
            s.sourceUri === uri &&
            !record.evidence.some((e) => e.raw === s.rawContent),
        );
        record.evidence.push({
          uri,
          raw: step?.rawContent || "",
          summary: JSON.parse(entry.detail || "{}") as ExtractedSummary,
        });
      }
      if (entry.type === "HOOK_VERDICT" && decision) {
        decision.final = entry.verdict!;
        const target = decision;
        pendingRefreshes.push(
          Promise.all([
            d2guardApi.getSessionTelemetry(id),
            desktopApi.metrics(id),
          ])
            .then(([state, metrics]) => {
              target.metric = metrics.calls.find(
                (m) => m.call_id === target.response.call_id,
              );
              target.coverage = Math.max(
                0,
                ...Object.values(state.accumulated_outbound).map(
                  (x) => x.coverage_ratio,
                ),
              );
              record.telemetry = state;
              publish();
            })
            .catch(() => {}),
        );
      }
      publish();
    };
    try {
      await d2guardApi.toggleArmor(id, armor);
      setSession(id);
      sessionRef.current = id;
      setTelemetry(undefined);
      const onAsk = (context: AskApprovalContext) => setAsk(context);
      const harness = new AgentHarness(
        id,
        new D2GuardHook(id, "main", onAsk),
        onLog,
        (response) => {
          decision = {
            response: { ...response, approval_token: null },
            tool: action?.tool || "",
            args: action?.args || {},
            final: response.verdict,
            elapsed: performance.now() - (action?.start || performance.now()),
            time: new Date().toLocaleTimeString(),
          };
          record.decisions.push(decision);
          publish();
        },
        async (name) => {
          const response = await fetch(
            new URL(`fixtures/${name}`, document.baseURI),
          );
          if (!response.ok)
            throw new Error(`测试输入读取失败: ${response.status}`);
          const raw = await response.text();
          record.evidence.push({ uri: String(action?.args.path || name), raw });
          publish();
          return raw;
        },
      );
      harness.setAskApprovalHandler(onAsk);
      if (typeof input === "string") {
        const planned = input.trim().startsWith("{")
          ? input
          : (await desktopApi.plan(input)).task;
        await harness.runFreeTask(planned);
      } else await harness.runPlaybook(input);
      await Promise.all(pendingRefreshes);
      record.evidence = (await desktopApi.evidence(id)).items;
      const metrics = await desktopApi.metrics(id);
      record.decisions.forEach((d) => {
        d.metric = metrics.calls.find((m) => m.call_id === d.response.call_id);
      });
      record.status = "complete";
      await refresh();
    } catch (e) {
      record.status = "error";
      setError(String(e));
      publish();
    } finally {
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
            href="#overview"
            onClick={(e) => {
              e.preventDefault();
              setPage("overview");
            }}
          >
            <Logo />
            <div>
              <strong>
                双镜 <span>D²Guard</span>
              </strong>
              <small>AGENT SECURITY DESK</small>
            </div>
          </a>
          <button className="new-task" onClick={() => setPage("workbench")}>
            <SquareTerminal size={17} />
            <span>开始一个任务</span>
            <span className="shortcut">↗</span>
          </button>
          <div className="nav-caption">
            工作空间 <span>WORKSPACE</span>
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
          <div className="sidebar-bottom">
            <div className={`guard-card ${armor ? "on" : ""}`}>
              <div>
                <ShieldCheck size={18} />
                <strong>{armor ? "边界已接管" : "准备好守住边界"}</strong>
              </div>
              <p>
                {armor
                  ? "D¹ 快慢双系统\nD² 增量状态流"
                  : "启用双镜，为 Agent 加上一层安全铠甲。"}
              </p>
              <button
                disabled={!ready || busy || toggling || !online}
                aria-label={armor ? "关闭双镜铠甲" : "启动双镜铠甲"}
                onClick={toggle}
              >
                {armor ? "关闭双镜铠甲" : "启动双镜铠甲"}
                <ArrowUpRight size={15} />
              </button>
            </div>
            <div className="local-profile">
              <div className="avatar">D²</div>
              <div>
                <strong>本地工作空间</strong>
                <small>LOCAL · v2.0</small>
              </div>
              <CircleHelp size={16} />
            </div>
          </div>
        </aside>
        <div className="workspace">
          <header className="topbar">
            <div className="breadcrumb">
              工作空间 <span>/</span>{" "}
              <strong>{navigation.find((n) => n[0] === page)?.[1]}</strong>
            </div>
            <div className="top-status">
              <span className={`status-dot ${online ? "online" : ""}`} />
              <span>{online ? "内核在线" : "内核离线"}</span>
              <code>{__D2GUARD_MANAGED__ ? '算力机 · 同源 API' : BASE_URL.replace('http://', '')}</code>
              <i />
              <span className={`mode-label ${armor ? "green" : ""}`}>
                {armor ? <ShieldCheck size={15} /> : <Shield size={15} />}{" "}
                {armor ? "铠甲模式" : "普通模式"}
              </span>
            </div>
          </header>
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
                run={current}
                telemetry={telemetry}
                busy={busy}
                ready={ready && online && !toggling}
                onRun={run}
                onReset={reset}
                config={config}
                onConfig={setConfig}
              />
            )}
            {page === "scenarios" && (
              <ScenarioLibrary busy={busy || !ready || !online} onRun={run} />
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
