import { ActionVerdictResponse, BASE_URL, Verdict } from "./d2guardClient";
import type { Scenario } from "../desk/types";

export type AgentMode = "live" | "replay" | "action";
export type AgentRunStatus = "running" | "waiting_approval" | "complete" | "error" | "cancelled";
export interface RunOptions {
  mode?: "live" | "action";
  clean?: boolean;
  workspacePath?: string;
}
export interface AgentRunRequest {
  task?: string;
  session_id?: string;
  armor_enabled: boolean;
  mode: AgentMode;
  scenario_id?: string;
  clean?: boolean;
  workspace_path?: string;
  action?: { tool_name: string; tool_args: Record<string, unknown> };
  scenario?: Scenario;
}
export interface AgentEvent {
  seq: number;
  id: string;
  session_id: string;
  timestamp: string | number;
  event_type: "USER" | "PLAN" | "SOURCE" | "TOOL_CALL" | "HOOK_VERDICT" | "TOOL_RESULT" | "ARTIFACT" | "SYSTEM" | "ERROR";
  title: string;
  detail?: string;
  call_id?: string;
  tool_name?: string;
  tool_args?: Record<string, unknown>;
  verdict?: Verdict;
  executed?: boolean;
  execution_success?: boolean;
  payload: Record<string, unknown> & { response?: ActionVerdictResponse; final?: Verdict };
}
export interface AgentRunResult {
  task_completed: boolean;
  final_answer: string;
  attack_succeeded: boolean | null;
  attack_prevented: boolean | null;
  artifacts: string[];
  outbound_receipts: Record<string, unknown>[];
  received_bytes: number;
  objective_evidence?: Record<string, unknown>;
  comparison_id?: string;
  [key: string]: unknown;
}
export interface AgentRunSnapshot {
  run_id: string;
  session_id: string;
  status: AgentRunStatus;
  mode: AgentMode;
  workspace_path: string;
  events: AgentEvent[];
  next_cursor: number;
  pending_approval?: {
    call_id: string;
    tool_name: string;
    tool_args: Record<string, unknown>;
    current_plan: string;
    verdict_response: ActionVerdictResponse;
  };
  result?: AgentRunResult;
  error?: string;
}
async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}/api/desktop/agent/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(typeof data.detail === "string" ? data.detail : `Agent 服务返回 ${response.status}`);
  }
  return response.json();
}
export const agentApi = {
  scenarios: () => request<{ scenarios: Scenario[] }>("scenarios"),
  saveScenarios: (scenarios: Scenario[] | Scenario) => request<{ ok: boolean; count: number }>("scenarios", scenarios),
  deleteScenario: async (scenarioId: string) => {
    const response = await fetch(`${BASE_URL}/api/desktop/agent/scenarios/${encodeURIComponent(scenarioId)}`, {
      method: "DELETE",
      signal: AbortSignal.timeout(30000),
    });
    if (!response.ok) throw new Error("删除失败");
    return response.json() as Promise<{ ok: boolean }>;
  },
  start: (body: AgentRunRequest) => request<Pick<AgentRunSnapshot, "run_id" | "session_id" | "status" | "mode" | "workspace_path">>("runs", body),
  poll: (runId: string, cursor: number) => request<AgentRunSnapshot>(`runs/${encodeURIComponent(runId)}?after=${cursor}`),
  approve: (runId: string, callId: string, approved: boolean) => request<{ ok: boolean }>(`runs/${encodeURIComponent(runId)}/approval`, { call_id: callId, user_approved: approved }),
  cancel: (runId: string) => request<{ ok: boolean }>(`runs/${encodeURIComponent(runId)}/cancel`, {}),
};
