import {
  Activity,
  ArrowUpRight,
  ShieldCheck,
  Zap,
  TrendingUp,
  ArrowRight,
} from "lucide-react";
import { Run, Decision, pct, ms } from "./types";
import { PageHeading, Panel, Empty, Badge } from "./ui";
const policyGroups = [
  ["POL-FS-WRITE", "POL-FS-WRITE-SENSITIVE"],
  ["POL-NET-EXFIL", "POL-NET-SECRET-EXFIL"],
  ["POL-EXEC-RESTRICT", "POL-EXEC-RESTRICT"],
  ["POL-GIT-NO-PUSH", "POL-GIT-REVIEW-NO-PUSH"],
  ["POL-SUBAGENT-LEAK", "POL-SUBAGENT-SECRET-LEAK"],
];
function LineChart({
  series,
  unit = "",
  fixedMax,
}: {
  series: { values: (number | undefined)[]; name: string; color: string }[];
  unit?: string;
  fixedMax?: number;
}) {
  const all = series
    .flatMap((s) => s.values)
    .filter((n): n is number => n !== undefined);
  const max = fixedMax ?? Math.max(1, ...all) * 1.15;
  const count = Math.max(1, ...series.map((s) => s.values.length));
  const left = unit === "ms" ? 100 : 48;
  const x = (i: number) =>
    left + (count === 1 ? 0 : i / (count - 1)) * (668 - left);
  const y = (n: number) => 152 - (n / max) * 120;
  return (
    <>
      <div className="chart-legend">
        {series.map((s) => (
          <span key={s.name}>
            <i style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
      <svg
        viewBox="0 0 700 185"
        className="line-chart"
        role="img"
        aria-label={series.map((s) => s.name).join("、")}
      >
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line
              x1={left}
              x2="670"
              y1={y(t * max)}
              y2={y(t * max)}
              stroke="#e9ede9"
              strokeDasharray="3 5"
            />
            <text x={left - 10} y={y(t * max) + 4} textAnchor="end">
              {(t * max).toFixed(unit === "ms" ? 2 : 0)}
              {unit === "ms" ? " ms" : unit}
            </text>
          </g>
        ))}
        {series.map((s) => {
          const segments: { n: number; i: number }[][] = [];
          s.values.forEach((n, i) => {
            if (n === undefined) {
              segments.push([]);
            } else {
              if (!segments.length) segments.push([]);
              segments.at(-1)!.push({ n, i });
            }
          });
          return (
            <g key={s.name}>
              {segments
                .filter((a) => a.length)
                .map((seg, j) => (
                  <g key={j}>
                    <path
                      d={seg
                        .map((p, i) => `${i ? "L" : "M"}${x(p.i)},${y(p.n)}`)
                        .join(" ")}
                      stroke={s.color}
                      strokeWidth="2.3"
                      strokeLinejoin="round"
                      fill="none"
                    />
                    {seg.map((p) => (
                      <circle
                        key={p.i}
                        cx={x(p.i)}
                        cy={y(p.n)}
                        r="3"
                        fill={s.color}
                      >
                        <title>
                          动作 {p.i + 1} · {p.n.toFixed(2)}
                          {unit}
                        </title>
                      </circle>
                    ))}
                  </g>
                ))}
            </g>
          );
        })}
        <text x={left} y="177">
          {all.length ? "第 1 个动作" : "等待真实会话数据"}
        </text>
        <text x="670" y="177" textAnchor="end">
          {all.length ? `第 ${count} 个动作` : "—"}
        </text>
      </svg>
    </>
  );
}
export function Dashboard({
  runs,
  armor,
  onInspect,
  onRun,
}: {
  runs: Run[];
  armor: boolean;
  onInspect: (id: string, call?: string) => void;
  onRun: () => void;
}) {
  const rows = runs.flatMap((r) => r.decisions.map((d) => ({ d, r })));
  const ds = rows.map((x) => x.d);
  const attack = ds.filter((d) => d.response.matched_policy_id);
  const blocked = attack.filter((d) => d.final === "BLOCK");
  const compliant = ds.filter(
    (d) =>
      !d.response.matched_policy_id &&
      d.response.fast_mirror_label.action_alignment === "expected" &&
      d.response.verdict !== "ASK",
  );
  const mean = ds.length
    ? ds.reduce((s, d) => s + d.response.fast_mirror_label.latency_ms, 0) /
      ds.length
    : undefined;
  const slow = ds.filter((d) => d.response.slow_mirror_triggered).length;
  const policies = policyGroups.map(([name, id]) => ({
    name,
    hits: ds.filter((d) => d.response.matched_policy_id === id).length,
    blocks: ds.filter(
      (d) => d.response.matched_policy_id === id && d.final === "BLOCK",
    ).length,
  }));
  const max = Math.max(1, ...policies.map((p) => p.hits));
  const recent = rows
    .filter((x) => x.d.final === "BLOCK")
    .slice(-5)
    .reverse();
  return (
    <>
      <PageHeading
        eyebrow="SECURITY OVERVIEW"
        title="防护总览"
        detail="查看任务、策略命中与拦截记录。"
      >
        <span className="live-label">
          <span className="status-dot online" />
          实时会话统计
        </span>
        <button onClick={onRun}>
          进入工作台运行场景
          <ArrowUpRight size={16} />
        </button>
      </PageHeading>
      <div className="overview-banner">
        <div className="banner-symbol">
          <ShieldCheck size={28} />
        </div>
        <div>
          <h3>
            {armor
              ? "防护模式已开启"
              : "普通模式"}
          </h3>
          <p>
            {armor
              ? "查看当前会话的工具调用与裁决记录。"
              : "运行场景，查看工具调用与裁决过程。"}
          </p>
        </div>
        <span className="banner-mark">D¹ + D²</span>
      </div>
      <div className="kpi-grid">
        <div className="kpi">
          <div>
            执行任务 / 动作 <Activity size={17} />
          </div>
          <strong>
            {runs.length}
            <em>/ {ds.length}</em>
          </strong>
          <small>
            {runs.filter((r) => r.status === "complete").length}{" "}
            个任务已完成审计
          </small>
        </div>
        <div className="kpi">
          <div>
            攻击拦截率 <ShieldCheck size={17} />
          </div>
          <strong>
            {attack.length ? pct(blocked.length / attack.length) : "—"}
          </strong>
          <small>
            {blocked.length} / {attack.length} 个命中策略动作被阻断
          </small>
        </div>
        <div className="kpi">
          <div>
            合规任务成功率 <TrendingUp size={17} />
          </div>
          <strong>
            {compliant.length
              ? pct(
                  compliant.filter((d) => d.final === "ALLOW").length /
                    compliant.length,
                )
              : "—"}
          </strong>
          <small>口径：合规工具申请获准比例</small>
        </div>
        <div className="kpi">
          <div>
            快镜平均耗时 <Zap size={17} />
          </div>
          <strong>
            {mean === undefined ? "—" : mean.toFixed(2)}
            <em>ms</em>
          </strong>
          <small>System 1 · 慢镜复核 {slow} 次</small>
        </div>
      </div>
      <div className="dashboard-grid">
        <Panel
          title="语义策略统计"
          subtitle="五大核心策略 · 命中与最终阻断"
          action={<span className="subtle-tag">累计 {ds.length} 次裁决</span>}
        >
          <div className="chart-legend">
            <span>
              <i style={{ background: "#c5d8d0" }} />
              触发
            </span>
            <span>
              <i style={{ background: "#38866d" }} />
              阻断
            </span>
          </div>
          <div className="policy-bars">
            {policies.map((p) => (
              <div className="policy-bar" key={p.name}>
                <code>{p.name}</code>
                <div>
                  <div className="bar-track">
                    <span
                      style={{
                        width: `${(p.hits / max) * 100}%`,
                        background: "#c5d8d0",
                      }}
                    />
                    <b>{p.hits}</b>
                  </div>
                  <div className="bar-track">
                    <span
                      style={{
                        width: `${(p.blocks / max) * 100}%`,
                        background: "#38866d",
                      }}
                    />
                    <b>{p.blocks}</b>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="防护效能对比" subtitle="同一策略口径 · 越权动作阻断率">
          <div className="comparison-chart">
            {[false, true].map((mode) => {
              const actions = rows.filter(
                (x) => x.r.armor === mode && x.d.response.matched_policy_id,
              );
              const n = actions.length
                ? actions.filter((x) => x.d.final === "BLOCK").length /
                  actions.length
                : 0;
              return (
                <div key={String(mode)}>
                  <strong>{actions.length ? pct(n) : "—"}</strong>
                  <div className="comparison-track">
                    <div
                      style={{
                        height: `${Math.max(actions.length ? 2 : 0, n * 100)}%`,
                      }}
                      className={mode ? "guarded" : ""}
                    />
                  </div>
                  <b>{mode ? "双镜 D²Guard 防护" : "无防护正常 Agent"}</b>
                  <small>
                    {actions.length
                      ? `${actions.length} 个越权样本`
                      : "尚无运行样本"}
                  </small>
                </div>
              );
            })}
          </div>
        </Panel>
      </div>
      <div className="dashboard-grid equal">
        <Panel title="风险评分演进" subtitle="Risk Score · 按真实动作顺序">
          <LineChart
            fixedMax={100}
            unit="%"
            series={[
              {
                name: "风险评分",
                color: "#b58b51",
                values: ds.map((d) => d.response.risk_score * 100),
              },
            ]}
          />
        </Panel>
        <Panel
          title="快慢镜响应延迟"
          subtitle="独立内核实测 · 未触发慢镜时留空"
        >
          <LineChart
            unit="ms"
            series={[
              {
                name: "快镜 System 1",
                color: "#3b8b71",
                values: ds.map((d) => d.response.fast_mirror_label.latency_ms),
              },
              {
                name: "慢镜 System 2",
                color: "#a58bc1",
                values: ds.map((d) => d.metric?.slow_latency_ms ?? undefined),
              },
            ]}
          />
        </Panel>
      </div>
      <Panel
        title="敏感凭据外发覆盖率"
        subtitle="Exfil Coverage Ratio · 当前动作的单域名最高覆盖率，50% 为阻断阈值"
      >
        <LineChart
          fixedMax={100}
          unit="%"
          series={[
            {
              name: "累计覆盖率",
              color: "#498d9b",
              values: ds.map((d) =>
                d.coverage === undefined ? undefined : d.coverage * 100,
              ),
            },
            { name: "阻断阈值", color: "#cfab78", values: ds.map(() => 50) },
          ]}
        />
      </Panel>
      <Panel
        title="近期拦截事件"
        subtitle="查看近期拦截动作与裁决依据"
        action={<span className="small muted">点击记录查看详情</span>}
      >
        {recent.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>时间 / 场景</th>
                  <th>工具动作</th>
                  <th>匹配策略</th>
                  <th>裁决</th>
                  <th>耗时</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {recent.map(({ d, r }) => (
                  <tr
                    key={d.response.call_id}
                    onClick={() => onInspect(r.id, d.response.call_id)}
                  >
                    <td>
                      <b>{r.title}</b>
                      <small>
                        {d.time} · {r.armor ? "铠甲模式" : "普通模式"}
                      </small>
                    </td>
                    <td>
                      <code>{d.tool}</code>
                    </td>
                    <td>
                      <code>{d.response.matched_policy_id || "用户拒绝"}</code>
                    </td>
                    <td>
                      <Badge value={d.final} />
                    </td>
                    <td>{ms(d.response.fast_mirror_label.latency_ms)}</td>
                    <td>
                      <button
                        className="icon-button"
                        aria-label={`查看 ${d.tool} 拦截详情`}
                      >
                        <ArrowRight size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="暂无拦截记录"
            detail="运行场景后，拦截记录将显示在这里。"
          />
        )}
      </Panel>
      <p className="footnote">
        统计范围：本次桌面打开后的全部会话。合规成功指内核授权通过与任务目标闭环；真实运行在隔离沙箱中执行工具并检验物理后果。没有样本的指标保留空值。
      </p>
    </>
  );
}
