import { useEffect, useState } from "react";
import { BASE_URL } from '../api/d2guardClient';
import { Check, Cpu, Server, SlidersHorizontal, RefreshCw } from "lucide-react";
import { desktopApi, ModelConfig, RuntimeHealth } from "./desktopApi";
import { Decision, ms, readLocal } from "./types";
import { Modal, PageHeading, Panel } from "./ui";
export type { ModelConfig } from "./desktopApi";
export const loadModelConfig = (): ModelConfig =>
  readLocal("d2guard.model-config", {
    base_url: "",
    main_model: "deepseek-chat",
    slow_model: "deepseek-chat",
  });
export function ModelForm({
  config,
  onConfig,
}: {
  config: ModelConfig;
  onConfig: (c: ModelConfig) => void;
}) {
  const [draft, setDraft] = useState(config);
  const [models, setModels] = useState<string[]>(
    readLocal("d2guard.models", []),
  );
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    desktopApi
      .config()
      .then((c) => {
        if (alive) {
          setDraft(c);
          onConfig(c);
        }
      })
      .catch((e) => {
        if (alive) setError(String(e));
      });
    return () => {
      alive = false;
    };
  }, []);
  const update = (key: keyof ModelConfig, value: string) =>
    setDraft((c) => ({ ...c, [key]: value, synced: false }));
  const test = async () => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const r = await desktopApi.test(draft);
      setModels(r.models);
      localStorage.setItem("d2guard.models", JSON.stringify(r.models));
      setMessage(r.message);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  const save = async () => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const saved = await desktopApi.save(draft);
      onConfig(saved);
      setDraft(saved);
      localStorage.setItem("d2guard.model-config", JSON.stringify(saved));
      setMessage("已保存到本地内核，主模型与慢镜配置立即生效");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <form
      className="model-form"
      onSubmit={(e) => {
        e.preventDefault();
        void save();
      }}
    >
      <div className="info-note">
        <Cpu size={18} />
        <span>
          模型辅助规划与复核，五条安全策略始终由内核裁决。未配置密钥时自动使用本地启发式。
        </span>
      </div>
      {__D2GUARD_MANAGED__ && <p className="info-note">公共体验站的模型由管理员统一配置。下载安装桌面版可设置个人模型。</p>}
      <fieldset disabled={__D2GUARD_MANAGED__} style={{ border: 0, padding: 0, margin: 0, display: 'contents' }}>
      <label>
        API 协议
        <select
          value={draft.api_style || "chat_completions"}
          onChange={(e) => update("api_style", e.target.value)}
        >
          <option value="chat_completions">
            Chat Completions · /chat/completions
          </option>
          <option value="responses">Responses · /responses</option>
        </select>
      </label>
      <label>
        Base URL
        <input
          placeholder="https://api.deepseek.com/v1"
          value={draft.base_url}
          onChange={(e) => update("base_url", e.target.value)}
        />
      </label>
      <label>
        API Key{" "}
        <span className="muted">
          {draft.has_api_key
            ? "已保存在本地内核；留空保留现有密钥"
            : "可选 · 密码输入"}
        </span>
        <input
          type="password"
          autoComplete="new-password"
          placeholder={draft.has_api_key ? "•••••••• 已配置" : "输入 API Key"}
          value={draft.api_key || ""}
          onChange={(e) => update("api_key", e.target.value)}
        />
      </label>
      <div className="row-between">
        <label className="check-label">
          <input
            type="checkbox"
            checked={draft.clear_key || false}
            onChange={(e) =>
              setDraft((c) => ({ ...c, clear_key: e.target.checked }))
            }
          />
          清除已保存密钥
        </label>
        <button type="button" onClick={test} disabled={busy}>
          <RefreshCw size={14} />
          {busy ? "连接中…" : "拉取/测试模型"}
        </button>
      </div>
      <div className="form-grid">
        {(["main_model", "slow_model"] as const).map((key, i) => (
          <label key={key}>
            {i ? "慢镜裁判模型" : "当前主模型"}
            <select
              aria-label={i ? "慢镜裁判模型" : "当前主模型"}
              value={draft[key]}
              onChange={(e) => update(key, e.target.value)}
            >
              {[...new Set([draft[key], ...models])]
                .filter(Boolean)
                .map((m) => (
                  <option key={m}>{m}</option>
                ))}
            </select>
          </label>
        ))}
      </div>
      <p className="small muted">
        API Key
        保存在本机内核数据库，不回传浏览器，也不写入导出报告。模型列表使用真实服务接口。
      </p>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="success-note">
          <Check size={15} />
          {message}
        </p>
      )}
      <button type="submit" className="primary" disabled={busy}>
        保存并同步后端
      </button>
      </fieldset>
    </form>
  );
}
export function ModelPopover(props: {
  config: ModelConfig;
  onConfig: (c: ModelConfig) => void;
  onClose: () => void;
}) {
  return (
    <Modal title="模型接入与选择" onClose={props.onClose}>
      <ModelForm {...props} />
    </Modal>
  );
}
export function SettingsPage({
  online,
  config,
  onConfig,
  latest,
}: {
  online: boolean;
  config: ModelConfig;
  onConfig: (c: ModelConfig) => void;
  latest?: Decision;
}) {
  const [health, setHealth] = useState<RuntimeHealth>();
  const [policies, setPolicies] = useState<{
    yaml: string;
    rules: { id: string; tools: string[] }[];
  }>();
  const [error, setError] = useState("");
  const refresh = async () => {
    try {
      const [h, p] = await Promise.all([
        desktopApi.health(),
        desktopApi.policies(),
      ]);
      setHealth(h);
      setPolicies(p);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    void refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, []);
  return (
    <>
      <PageHeading
        eyebrow="PREFERENCES"
        title="设置与接入"
        detail="配置模型服务，查看运行环境与策略。"
      >
        <button onClick={refresh}>
          <RefreshCw size={15} />
          刷新状态
        </button>
      </PageHeading>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <div className="settings-grid">
        <Panel title="模型服务" subtitle="OpenAI 兼容接口 · 配置实时同步">
          <ModelForm config={config} onConfig={onConfig} />
        </Panel>
        <div className="stack">
          <Panel title="运行环境" subtitle="来自本地内核的实时健康状态">
            <div className="health-item">
              <Server />
              <div>
                <strong>Core API</strong>
                <p>{BASE_URL}</p>
              </div>
              <span className={`badge ${online ? "allow" : "block"}`}>
                {online ? "在线" : "离线"}
              </span>
            </div>
            <div className="health-item">
              <Cpu />
              <div>
                <strong>Laya / System 1</strong>
                <p>
                  {health?.fast.model_loaded
                    ? "本地模型已载入"
                    : "本地启发式 · 未载入权重"}
                </p>
              </div>
              <span className="badge neutral">
                {health?.fast.status || "检测中"}
              </span>
            </div>
            <dl className="key-values">
              <dt>推理后端</dt>
              <dd>{health?.fast.backend || "—"}</dd>
              <dt>推理预算</dt>
              <dd>{health ? ms(health.fast.budget_ms) : "—"}</dd>
              <dt>最近快镜耗时</dt>
              <dd>
                {latest
                  ? ms(latest.response.fast_mirror_label.latency_ms)
                  : "等待裁决"}
              </dd>
              <dt>工作线程</dt>
              <dd>{health?.fast.busy ? "忙碌" : "空闲"}</dd>
              <dt>最近异常</dt>
              <dd>{health?.fast.last_error || "无"}</dd>
              <dt>慢镜服务</dt>
              <dd>
                {health?.slow.configured ? "远程模型已配置" : "本地结构化复核"}
              </dd>
            </dl>
          </Panel>
          <div className="quiet-card">
            <SlidersHorizontal size={22} />
            <h3>策略优先，模型辅助</h3>
            <p>
              主模型产生工具申请，快镜筛查与慢镜复核协同工作。最终放行、挂起和阻断均由真实内核返回。
            </p>
          </div>
        </div>
      </div>
      <Panel
        title="五大语义策略 DSL"
        subtitle="实时读取内核当前 YAML · 只读检视"
      >
        <div className="policy-list">
          {policies?.rules.map((rule, i) => (
            <details key={rule.id} open={i === 0}>
              <summary>
                <span className="policy-index">0{i + 1}</span>
                <strong>{rule.id}</strong>
                <code>{rule.tools.join(" / ")}</code>
              </summary>
              <pre>
                {policies.yaml
                  .split(/(?=  - id: )/)
                  .find((s) => s.includes(rule.id)) || ""}
              </pre>
            </details>
          ))}
        </div>
      </Panel>
    </>
  );
}
