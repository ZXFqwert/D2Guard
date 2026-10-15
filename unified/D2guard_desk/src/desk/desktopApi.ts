import { BASE_URL } from "../api/d2guardClient";
export interface ModelConfig {
  api_style?: "chat_completions" | "responses";
  timeout_seconds?: number;
  base_url: string;
  api_key?: string;
  main_model: string;
  slow_model: string;
  has_api_key?: boolean;
  clear_key?: boolean;
  synced?: boolean;
}
export interface MirrorMetric {
  call_id: string;
  fast_latency_ms: number;
  slow_latency_ms: number | null;
  slow_mode: string;
}
export interface RuntimeHealth {
  fast: {
    backend: string;
    model_loaded: boolean;
    status: string;
    last_error: string | null;
    busy: boolean;
    budget_ms: number;
  };
  slow: { configured: boolean; model: string; mode: string };
}
async function request<T>(path: string, data?: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}/api/desktop/${path}`, {
    method: data === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    ...(data === undefined ? {} : { body: JSON.stringify(data) }),
    signal: AbortSignal.timeout(28000),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(
      typeof detail.detail === "string"
        ? detail.detail
        : `配置服务返回 ${res.status}`,
    );
  }
  return res.json();
}
const payload = (c: ModelConfig) => ({
  base_url: c.base_url,
  main_model: c.main_model,
  slow_model: c.slow_model,
  ...(c.api_key ? { api_key: c.api_key } : {}),
  clear_key: c.clear_key || false,
  api_style: c.api_style || "chat_completions",
  timeout_seconds: c.timeout_seconds || 20,
});
export const desktopApi = {
  config: () => request<ModelConfig>("models/config"),
  save: (c: ModelConfig) => request<ModelConfig>("models/config", payload(c)),
  test: (c: ModelConfig) =>
    request<{ models: string[]; mode: string; message: string }>(
      "models/test",
      payload(c),
    ),
  plan: (task: string) =>
    request<{ mode: string; task: string }>("models/plan", { task }),
  health: () => request<RuntimeHealth>("runtime/health"),
  metrics: (session: string) =>
    request<{ calls: MirrorMetric[] }>(
      `sessions/${encodeURIComponent(session)}/metrics`,
    ),
  evidence: (session: string) =>
    request<{ items: import("./types").Evidence[] }>(
      `sessions/${encodeURIComponent(session)}/evidence`,
    ),
  policies: () =>
    request<{ yaml: string; rules: { id: string; tools: string[] }[] }>(
      "policies",
    ),
};
