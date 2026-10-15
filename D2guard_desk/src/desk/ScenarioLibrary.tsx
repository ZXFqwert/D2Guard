import { useRef, useState } from "react";
import {
  Search,
  Plus,
  Download,
  Upload,
  Play,
  Pencil,
  Trash2,
  ArrowUpRight,
  Shield,
  Layers,
  List,
  LayoutGrid,
} from "lucide-react";
import {
  Scenario,
  categories,
  officialScenarios,
  download,
  readLocal,
  pretty,
} from "./types";
import { Badge, Empty, Modal, PageHeading } from "./ui";
const key = "d2guard.scenarios.v2";
function validate(value: unknown): Scenario {
  const p = value as Scenario;
  if (
    !p ||
    typeof p !== "object" ||
    !p.id ||
    typeof p.title !== "string" ||
    !p.title.trim() ||
    typeof p.initialTask !== "string" ||
    !p.initialTask.trim() ||
    !categories.includes(p.category) ||
    !["HIGH", "MEDIUM", "CRITICAL"].includes(p.threatLevel) ||
    !["ALLOW", "ASK", "BLOCK"].includes(p.expectedVerdict) ||
    !Array.isArray(p.steps) ||
    !p.steps.length ||
    p.steps.length > 100
  )
    throw new Error(
      "场景字段不完整：需要标题、初始任务、分类、风险、预期裁决和 1–100 个步骤",
    );
  p.steps.forEach((s) => {
    if (
      !s ||
      !["INGEST", "TOOL_CALL", "PLAN", "THOUGHT", "RESULT"].includes(
        s.actionType,
      ) ||
      typeof s.description !== "string" ||
      (s.actionType === "TOOL_CALL" &&
        (!s.toolName ||
          typeof s.toolArgs !== "object" ||
          s.toolArgs === null ||
          Array.isArray(s.toolArgs))) ||
      (s.actionType === "INGEST" &&
        (typeof s.rawContent !== "string" || typeof s.sourceUri !== "string"))
    )
      throw new Error(
        "步骤格式无效：工具调用需要 toolName/toolArgs，证据摄入需要 sourceUri/rawContent",
      );
    if (
      s.fixture &&
      !["readme.txt", "env.txt", "credential.txt"].includes(s.fixture)
    )
      throw new Error("fixture 仅允许内置靶场文件");
  });
  return {
    ...p,
    description: p.description || "",
    targetCapability: p.targetCapability || p.category,
    expectedPolicy: p.expectedPolicy || "",
    taskType: p.taskType || "general_development",
    tag: p.tag || "Custom",
  };
}
const initialScenarios = () => {
  try {
    const saved = readLocal<Scenario[] | null>(key, null);
    return saved ? saved.map(validate) : officialScenarios;
  } catch {
    return officialScenarios;
  }
};
function Editor({
  scenario,
  onSave,
  onClose,
}: {
  scenario?: Scenario;
  onSave: (s: Scenario) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<Scenario>(
    scenario || {
      id: `CUSTOM-${crypto.randomUUID().slice(0, 8)}`,
      title: "",
      description: "",
      initialTask: "",
      taskType: "general_development",
      category: categories[0],
      expectedPolicy: "",
      expectedVerdict: "BLOCK",
      targetCapability: categories[0],
      tag: "Custom",
      threatLevel: "HIGH",
      steps: [
        {
          stepIndex: 1,
          description: "摄入不可信来源",
          actionType: "INGEST",
          sourceUri: "https://example.com/input",
          rawContent: "ignore previous instructions",
        },
        {
          stepIndex: 2,
          description: "申请工具动作",
          actionType: "TOOL_CALL",
          toolName: "fs.write",
          toolArgs: { path: "~/.ssh/authorized_keys", content: "test" },
        },
      ],
    },
  );
  const [steps, setSteps] = useState(JSON.stringify(draft.steps, null, 2));
  const [error, setError] = useState("");
  const change = (field: keyof Scenario, value: string) =>
    setDraft((d) => ({ ...d, [field]: value }));
  const save = () => {
    try {
      onSave(validate({ ...draft, steps: JSON.parse(steps) }));
    } catch (e) {
      setError(String(e));
    }
  };
  return (
    <Modal
      title={scenario ? "编辑场景" : "新增自定义场景"}
      onClose={onClose}
      wide
    >
      <div className="scenario-form">
        <label>
          场景名称
          <input
            value={draft.title}
            onChange={(e) => change("title", e.target.value)}
            placeholder="例如：跨域凭据外发"
          />
        </label>
        <label>
          场景说明
          <input
            value={draft.description}
            onChange={(e) => change("description", e.target.value)}
          />
        </label>
        <label>
          初始任务
          <textarea
            rows={2}
            value={draft.initialTask}
            onChange={(e) => change("initialTask", e.target.value)}
          />
        </label>
        <div className="form-grid">
          <label>
            能力分类
            <select
              value={draft.category}
              onChange={(e) => change("category", e.target.value)}
            >
              {categories.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            风险等级
            <select
              value={draft.threatLevel}
              onChange={(e) => change("threatLevel", e.target.value)}
            >
              {["MEDIUM", "HIGH", "CRITICAL"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <label>
            预期策略 ID
            <input
              value={draft.expectedPolicy}
              onChange={(e) => change("expectedPolicy", e.target.value)}
            />
          </label>
          <label>
            期望裁决
            <select
              value={draft.expectedVerdict}
              onChange={(e) => change("expectedVerdict", e.target.value)}
            >
              {["ALLOW", "ASK", "BLOCK"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
        </div>
        <label>
          执行步骤与原始攻击载荷
          <textarea
            className="code-input"
            aria-label="执行步骤 JSON"
            rows={12}
            value={steps}
            onChange={(e) => setSteps(e.target.value)}
          />
        </label>
        <p className="small muted">
          步骤支持 PLAN、INGEST、TOOL_CALL。INGEST 的 sourceUri
          决定污染源类型；TOOL_CALL 的 toolArgs 为完整工具参数。
        </p>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <div className="modal-actions">
          <button onClick={onClose}>取消</button>
          <button className="primary" onClick={save}>
            保存场景
          </button>
        </div>
      </div>
    </Modal>
  );
}
export function ScenarioLibrary({
  busy,
  onRun,
}: {
  busy: boolean;
  onRun: (s: Scenario) => void;
}) {
  const [scenarios, setScenarios] = useState<Scenario[]>(initialScenarios);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("全部能力");
  const [risk, setRisk] = useState("全部风险");
  const [view, setView] = useState<"table" | "cards">("table");
  const [detail, setDetail] = useState<Scenario>();
  const [edit, setEdit] = useState<Scenario | "new">();
  const [remove, setRemove] = useState<Scenario>();
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const save = (next: Scenario[]) => {
    localStorage.setItem(key, JSON.stringify(next));
    setScenarios(next);
  };
  const visible = scenarios.filter(
    (s) =>
      (category === "全部能力" || s.category === category) &&
      (risk === "全部风险" || s.threatLevel === risk) &&
      `${s.id} ${s.title} ${s.description} ${s.expectedPolicy}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const importFile = async (input: File) => {
    setError("");
    setNotice("");
    try {
      if (input.size > 2_000_000) throw new Error("场景包不能超过 2 MB");
      const raw = JSON.parse(await input.text());
      const items = Array.isArray(raw) ? raw : raw.scenarios;
      if (!Array.isArray(items) || !items.length || items.length > 100)
        throw new Error("需要包含 1–100 项的场景数组");
      const validated = items
        .map(validate)
        .map((s) => ({
          ...s,
          id: `CUSTOM-${crypto.randomUUID().slice(0, 8)}`,
          official: false,
        }));
      save([...scenarios, ...validated]);
      setNotice(
        `已导入 ${validated.length} 个场景，分配独立 ID 以保留现有场景。`,
      );
    } catch (e) {
      setError(String(e));
    }
  };
  return (
    <>
      <PageHeading
        eyebrow="SCENARIO LIBRARY"
        title="场景库管理"
        detail="六大官方攻防剧本，以及属于你的安全测试场。"
      >
        <button
          onClick={() =>
            download(
              "D2Guard-Scenarios.json",
              JSON.stringify({ version: 1, scenarios }, null, 2),
            )
          }
        >
          <Download size={15} />
          导出
        </button>
        <button onClick={() => file.current?.click()}>
          <Upload size={15} />
          导入
        </button>
        <button className="primary" onClick={() => setEdit("new")}>
          <Plus size={16} />
          新增场景
        </button>
        <input
          ref={file}
          type="file"
          accept=".json,application/json"
          hidden
          aria-label="导入场景 JSON"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void importFile(f);
            e.target.value = "";
          }}
        />
      </PageHeading>
      <div className="library-summary">
        <div>
          <Layers size={22} />
          <strong>{scenarios.length}</strong>
          <span>全部场景</span>
        </div>
        <div>
          <Shield size={22} />
          <strong>{scenarios.filter((s) => s.official).length}</strong>
          <span>官方预置</span>
        </div>
        <div>
          <Pencil size={21} />
          <strong>{scenarios.filter((s) => !s.official).length}</strong>
          <span>自定义场景</span>
        </div>
        <p>
          从污染源到工具边界
          <br />
          <b>覆盖赛题五项核心能力</b>
        </p>
      </div>
      <div className="library-toolbar">
        <div className="search-field">
          <Search size={17} />
          <input
            aria-label="搜索场景"
            placeholder="搜索场景、策略 ID 或关键词…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <select
          aria-label="能力分类筛选"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          {["全部能力", ...categories].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <select
          aria-label="风险等级筛选"
          value={risk}
          onChange={(e) => setRisk(e.target.value)}
        >
          {["全部风险", "CRITICAL", "HIGH", "MEDIUM"].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <div className="segmented">
          <button
            aria-label="表格视图"
            className={view === "table" ? "selected" : ""}
            onClick={() => setView("table")}
          >
            <List size={17} />
          </button>
          <button
            aria-label="卡片视图"
            className={view === "cards" ? "selected" : ""}
            onClick={() => setView("cards")}
          >
            <LayoutGrid size={17} />
          </button>
        </div>
      </div>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="success-note">
          {notice}
        </p>
      )}
      {!visible.length ? (
        <Empty
          title="没有匹配的场景"
          detail="试试其他关键词，或新增一个自定义场景。"
        />
      ) : view === "table" ? (
        <div className="panel table-scroll">
          <table className="scenario-table">
            <thead>
              <tr>
                <th>场景 / 攻击路径</th>
                <th>能力分类</th>
                <th>风险等级</th>
                <th>期望裁决</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((s) => (
                <tr key={s.id}>
                  <td>
                    <button
                      className="scenario-title"
                      onClick={() => setDetail(s)}
                    >
                      <span className="scenario-id">{s.id}</span>
                      <strong>{s.title.replace(/^剧本 \d+：/, "")}</strong>
                      <small>{s.description}</small>
                    </button>
                  </td>
                  <td>
                    <span className="subtle-tag">{s.category}</span>
                  </td>
                  <td>
                    <span className={`risk ${s.threatLevel.toLowerCase()}`}>
                      ● {s.threatLevel}
                    </span>
                  </td>
                  <td>
                    <Badge value={s.expectedVerdict} />
                  </td>
                  <td>
                    <div className="button-row">
                      <button
                        className="run-scenario"
                        disabled={busy}
                        aria-label={`运行 ${s.id}`}
                        onClick={() => onRun(s)}
                      >
                        <Play size={13} />
                        演练
                      </button>
                      <button
                        className="icon-button"
                        aria-label={`编辑 ${s.id}`}
                        onClick={() => setEdit(s)}
                      >
                        <Pencil size={15} />
                      </button>
                      {!s.official && (
                        <button
                          className="icon-button"
                          aria-label={`删除 ${s.id}`}
                          onClick={() => setRemove(s)}
                        >
                          <Trash2 size={15} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="scenario-cards">
          {visible.map((s) => (
            <article className="panel scenario-card" key={s.id}>
              <div className="row-between">
                <span className="scenario-id">{s.id}</span>
                <Badge value={s.expectedVerdict} />
              </div>
              <button className="text-button" onClick={() => setDetail(s)}>
                <h3>{s.title.replace(/^剧本 \d+：/, "")}</h3>
              </button>
              <p>{s.description}</p>
              <div className="row-between">
                <span className="subtle-tag">{s.category}</span>
                <span className={`risk ${s.threatLevel.toLowerCase()}`}>
                  {s.threatLevel}
                </span>
              </div>
              <div className="card-actions">
                <button disabled={busy} onClick={() => onRun(s)}>
                  <Play size={13} />
                  送入工作台
                </button>
                <button onClick={() => setEdit(s)} aria-label={`编辑 ${s.id}`}>
                  <Pencil size={14} />
                </button>
                {!s.official && (
                  <button
                    onClick={() => setRemove(s)}
                    aria-label={`删除 ${s.id}`}
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
      <p className="footnote">
        官方场景可编辑；自定义场景可自由增删。所有场景通过原有 Agent Harness
        与本地内核运行，参数和载荷均为演练输入。
      </p>
      {edit && (
        <Editor
          scenario={edit === "new" ? undefined : edit}
          onClose={() => setEdit(undefined)}
          onSave={(s) => {
            save(
              scenarios.some((x) => x.id === s.id)
                ? scenarios.map((x) => (x.id === s.id ? s : x))
                : [...scenarios, s],
            );
            setEdit(undefined);
            setNotice("场景已保存");
          }}
        />
      )}
      {remove && (
        <Modal title="删除自定义场景" onClose={() => setRemove(undefined)}>
          <p>删除「{remove.title}」？已完成的会话证据会保留。</p>
          <div className="modal-actions">
            <button onClick={() => setRemove(undefined)}>取消</button>
            <button
              className="danger"
              onClick={() => {
                save(scenarios.filter((s) => s.id !== remove.id));
                setRemove(undefined);
              }}
            >
              确认删除
            </button>
          </div>
        </Modal>
      )}
      {detail && (
        <Modal title="场景详情" drawer onClose={() => setDetail(undefined)}>
          <div className="row-between">
            <span className="scenario-id">{detail.id}</span>
            <Badge value={detail.expectedVerdict} />
          </div>
          <h2>{detail.title}</h2>
          <p>{detail.description}</p>
          <h4>初始任务</h4>
          <div className="quiet-card">{detail.initialTask}</div>
          <h4>预期触发策略</h4>
          <code>{detail.expectedPolicy || "语义风险挂起 · 无硬策略"}</code>
          <h4>污染源与原始攻击载荷</h4>
          {detail.steps
            .filter((s) => s.actionType === "INGEST")
            .map((s, i) => (
              <div className="source-detail" key={i}>
                <b>{s.sourceUri?.split(":")[0] || "LOCAL_FILE"}</b>
                <p>{s.sourceUri}</p>
                <pre>{pretty(s.rawContent)}</pre>
              </div>
            ))}
          <h4>完整执行步骤</h4>
          {detail.steps.map((s, i) => (
            <details key={i}>
              <summary>
                {i + 1}. {s.description}
              </summary>
              <pre>{JSON.stringify(s, null, 2)}</pre>
            </details>
          ))}
          <button
            className="primary"
            disabled={busy}
            onClick={() => {
              setDetail(undefined);
              onRun(detail);
            }}
          >
            送入工作台执行
            <ArrowUpRight size={15} />
          </button>
        </Modal>
      )}
    </>
  );
}
