import {
  ActionVerdictResponse,
  ExtractedSummary,
  TelemetrySnapshotResponse,
  Verdict,
} from "../api/d2guardClient";
import {
  ExecutionLogEntry,
  RedTeamPlaybook,
  RED_TEAM_PLAYBOOKS,
} from "../core/AgentHarness";

export type PageId =
  | "overview"
  | "workbench"
  | "scenarios"
  | "trace"
  | "settings";
export interface Evidence {
  event_id?: string;
  raw_tokens?: [number, number][];
  uri: string;
  raw: string;
  summary?: ExtractedSummary;
}
export interface Decision {
  metric?: import("./desktopApi").MirrorMetric;
  response: ActionVerdictResponse;
  tool: string;
  args: Record<string, unknown>;
  final: Verdict;
  elapsed: number;
  time: string;
  coverage?: number;
}
export interface Run {
  id: string;
  title: string;
  armor: boolean;
  started: string;
  logs: ExecutionLogEntry[];
  decisions: Decision[];
  evidence: Evidence[];
  telemetry?: TelemetrySnapshotResponse;
  status: "running" | "complete" | "error";
  scenarioId?: string;
}
export interface Scenario extends RedTeamPlaybook {
  category: string;
  expectedPolicy: string;
  expectedVerdict: Verdict;
  official?: boolean;
}
export const categories = [
  "多源注入",
  "语义对齐",
  "五大工具策略",
  "跨 MCP 溯源",
  "对抗混淆",
];
const meta = [
  ["多源注入", "POL-NET-SECRET-EXFIL"],
  ["五大工具策略", "POL-NET-SECRET-EXFIL"],
  ["对抗混淆", "POL-EXEC-RESTRICT"],
  ["语义对齐", "POL-GIT-REVIEW-NO-PUSH"],
  ["跨 MCP 溯源", "POL-SUBAGENT-SECRET-LEAK"],
  ["对抗混淆", ""],
];
export const officialScenarios: Scenario[] = RED_TEAM_PLAYBOOKS.map((p, i) => ({
  ...p,
  category: meta[i][0],
  expectedPolicy: meta[i][1],
  expectedVerdict: i === 5 ? "ASK" : "BLOCK",
  official: true,
}));
export const ms = (n: number) => `${n.toFixed(2)} ms`;
export const pct = (n: number) => `${(n * 100).toFixed(1)}%`;
export function download(
  name: string,
  content: string,
  type = "application/json",
) {
  const url = URL.createObjectURL(
    new Blob([content], { type: `${type};charset=utf-8` }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
export function readLocal<T>(key: string, fallback: T): T {
  try {
    return JSON.parse(localStorage.getItem(key) || "null") ?? fallback;
  } catch {
    return fallback;
  }
}
export function pretty(value: string | undefined) {
  if (!value) return "";
  try {
    return JSON.stringify(
      JSON.parse(value),
      (key, item) =>
        key.endsWith("latency_ms") && typeof item === "number"
          ? ms(item)
          : item,
      2,
    );
  } catch {
    return value;
  }
}
