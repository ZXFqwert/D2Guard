/**
 * D2Guard Client per d2guard_contract.json
 * Strictly connects to backend at http://127.0.0.1:8765
 * NO mock verdict in frontend!
 */

export const BASE_URL = 'http://127.0.0.1:8765';

export type CallLifecycleStage = 'MODEL_PROPOSED' | 'TOOL_PRE_EXEC' | 'TOOL_POST_EXEC';
export type EventType = 'USER_INPUT' | 'TOOL_CALL' | 'TOOL_RETURN' | 'SUBAGENT_SPAWN' | 'MEMORY_RECALL';
export type SourceType = 'USER' | 'WEB' | 'LOCAL_FILE' | 'CODE_ISSUE' | 'MCP_DESC' | 'MCP_RET' | 'MEMORY';
export type Verdict = 'ALLOW' | 'ASK' | 'BLOCK';
export type ContentNature = 'informational' | 'directive' | 'example' | 'uncertain';
export type ActionAlignment = 'expected' | 'ancillary' | 'deviant' | 'insufficient';
export type DagNodeType = 'SOURCE' | 'AGENT' | 'MCP_SERVER' | 'TOOL';
export type DagEdgeType = 'ACTUAL_CALL' | 'TAINT_INDUCE' | 'BLOCKED_ACTION';

export interface FastMirrorLabel {
  content_nature: ContentNature;
  action_alignment: ActionAlignment;
  latency_ms: number;
}

export interface ExtractedSummary {
  normalized_text: string;
  char_span: [number, number];
  token_span: [number, number];
  detected_secrets_count: number;
  fast_mirror_label: FastMirrorLabel;
}

export interface IngestEventRequest {
  event_id: string;
  session_id: string;
  timestamp: number;
  agent_id: string;
  parent_agent_id: string | null;
  call_id: string | null;
  stage: CallLifecycleStage;
  event_type: EventType;
  source_type: SourceType;
  source_uri: string;
  raw_content: string;
  current_plan: string;
  tool_name?: string | null;
  tool_args?: Record<string, any> | null;
}

export interface IngestEventResponse {
  status: string;
  event_id: string;
  extracted_summary: ExtractedSummary;
}

export interface DecideActionRequest {
  session_id: string;
  call_id: string;
  agent_id: string;
  tool_name: string;
  tool_args: Record<string, any>;
  current_plan: string;
}

export interface ActionVerdictResponse {
  call_id: string;
  verdict: Verdict;
  risk_score: number;
  matched_policy_id: string | null;
  fast_mirror_label: FastMirrorLabel;
  slow_mirror_triggered: boolean;
  explainable_report: string;
  approval_token: string | null;
  source_uri?: string;
  char_span?: [number, number];
  token_span?: [number, number];
}

export interface ApproveActionRequest {
  session_id: string;
  call_id: string;
  approval_token: string;
  user_approved: boolean;
}

export interface ApproveActionResponse {
  call_id: string;
  final_verdict: 'ALLOW' | 'BLOCK';
  reason: string;
}

export interface AnchorIntent {
  initial_task: string;
  task_type: string;
  intent_version?: number;
}

export interface SecretRecordItem {
  secret_id: string;
  source_path: string;
  chunks_total: number;
}

export interface OutboundDomainRecord {
  matched_chunks_count: number;
  coverage_ratio: number;
  blocked: boolean;
}

export interface DagNodeItem {
  id: string;
  type: DagNodeType;
  label: string;
  source_type?: SourceType;
  token_span?: [number, number];
  verdict?: Verdict;
  risk?: string;
}

export interface DagEdgeItem {
  from: string;
  to: string;
  edge_type: DagEdgeType;
}

export interface ImpactScope {
  protected_files: string[];
  blocked_domains: string[];
  blocked_git_repos: string[];
  accessed_credentials: string[];
}

export interface TelemetrySnapshotResponse {
  session_id: string;
  armor_enabled: boolean;
  anchor_intent: AnchorIntent | null;
  secret_ledger: SecretRecordItem[];
  accumulated_outbound: Record<string, OutboundDomainRecord>;
  dag_nodes: DagNodeItem[];
  dag_edges: DagEdgeItem[];
  impact_scope: ImpactScope;
}

export interface ToggleArmorRequest {
  armor_enabled: boolean;
}

export interface ToggleArmorResponse {
  session_id: string;
  armor_enabled: boolean;
}

class D2GuardClient {
  private baseUrl: string;

  constructor(baseUrl: string = BASE_URL) {
    this.baseUrl = baseUrl;
  }

  public async checkHealth(): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/openapi.json`, {signal: AbortSignal.timeout(3000)});
      if (!res.ok) return false;
      const schema = await res.json();
      return schema.info?.title === 'd2guard_core' && Boolean(schema.paths?.['/api/v1/actions/decide']);
    } catch {
      return false;
    }
  }

  public async ingestEvent(req: IngestEventRequest): Promise<IngestEventResponse> {
    const payload = {
      ...req,
      call_id: req.call_id || crypto.randomUUID(),
      tool_name: req.tool_name || '',
      tool_args: req.tool_args || {},
    };
    const res = await fetch(`${this.baseUrl}/api/v1/events/ingest`, {
      method: 'POST',
      signal: AbortSignal.timeout(30000),
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`Ingest failed [${res.status}]: ${errorText}`);
    }
    return res.json();
  }

  public async decideAction(req: DecideActionRequest): Promise<ActionVerdictResponse> {
    const res = await fetch(`${this.baseUrl}/api/v1/actions/decide`, {
      method: 'POST',
      signal: AbortSignal.timeout(30000),
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`Decide failed [${res.status}]: ${errorText}`);
    }
    return res.json();
  }

  public async approveAction(req: ApproveActionRequest): Promise<ApproveActionResponse> {
    const res = await fetch(`${this.baseUrl}/api/v1/actions/approve`, {
      method: 'POST',
      signal: AbortSignal.timeout(30000),
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`Approve failed [${res.status}]: ${errorText}`);
    }
    return res.json();
  }

  public async getSessionTelemetry(sessionId: string): Promise<TelemetrySnapshotResponse> {
    const res = await fetch(`${this.baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/telemetry`, {
      method: 'GET',
      signal: AbortSignal.timeout(30000),
      headers: { 'Accept': 'application/json' },
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`Telemetry failed [${res.status}]: ${errorText}`);
    }
    return res.json();
  }

  public async toggleArmor(sessionId: string, armorEnabled: boolean): Promise<ToggleArmorResponse> {
    const res = await fetch(`${this.baseUrl}/api/v1/sessions/${encodeURIComponent(sessionId)}/armor`, {
      method: 'POST',
      signal: AbortSignal.timeout(30000),
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ armor_enabled: armorEnabled }),
    });
    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`ToggleArmor failed [${res.status}]: ${errorText}`);
    }
    return res.json();
  }
}

export const d2guardApi = new D2GuardClient();
