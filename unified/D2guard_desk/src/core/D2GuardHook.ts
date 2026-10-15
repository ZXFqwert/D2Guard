import { d2guardApi, ActionVerdictResponse } from '../api/d2guardClient';

export interface AskApprovalContext {
  callId: string; sessionId: string; toolName: string; toolArgs: Record<string, any>;
  currentPlan: string; verdictResponse: ActionVerdictResponse; resolve: (approved: boolean) => void;
}
export type AskApprovalHandler = (context: AskApprovalContext) => void;
export interface ToolExecutionResult {
  success: boolean; blocked: boolean; verdict: 'ALLOW' | 'ASK' | 'BLOCK';
  output?: unknown; error?: string; verdictResponse: ActionVerdictResponse;
}

/** Every audit action must reach the kernel. Transport failures are errors, never local verdicts. */
export class D2GuardHook {
  constructor(private sessionId: string, private agentId = 'main', private onAskApproval?: AskApprovalHandler) {}
  setAskApprovalHandler(handler: AskApprovalHandler) { this.onAskApproval = handler; }
  setSessionId(id: string) { this.sessionId = id; }

  async interceptToolCall(callId: string, toolName: string, toolArgs: Record<string, any>,
    currentPlan: string, readFixture?: () => Promise<string>, parentAgentId: string | null = null): Promise<ToolExecutionResult> {
    const sessionId = this.sessionId;
    const event = { session_id: sessionId, timestamp: Date.now() / 1000, agent_id: this.agentId,
      parent_agent_id: parentAgentId, call_id: callId, event_type: 'TOOL_CALL' as const,
      source_type: 'USER' as const, source_uri: 'host://workbench',
      raw_content: `${toolName}(${JSON.stringify(toolArgs)})`, current_plan: currentPlan,
      tool_name: toolName, tool_args: toolArgs };
    for (const stage of ['MODEL_PROPOSED', 'TOOL_PRE_EXEC'] as const) {
      await d2guardApi.ingestEvent({ ...event, event_id: crypto.randomUUID(), stage });
    }
    const verdictResponse = await d2guardApi.decideAction({session_id: sessionId, call_id: callId,
      agent_id: this.agentId, tool_name: toolName, tool_args: toolArgs, current_plan: currentPlan});
    let final = verdictResponse.verdict;
    if (final === 'ASK') {
      const approved = await new Promise<boolean>((resolve) => {
        const timer = setTimeout(() => resolve(false), 60000);
        const finish = (value: boolean) => { clearTimeout(timer); resolve(value); };
        if (this.onAskApproval) this.onAskApproval({callId, sessionId, toolName, toolArgs,
          currentPlan, verdictResponse, resolve: finish});
        else finish(false);
      });
      const response = await d2guardApi.approveAction({session_id: sessionId, call_id: callId,
        approval_token: verdictResponse.approval_token!, user_approved: approved});
      final = response.final_verdict;
    }
    let output: string | undefined;
    // Only genuine fixture-file reads produce TOOL_POST_EXEC. Proposed destructive
    // actions are audited; the desk never invents successful OS/network execution.
    if (final === 'ALLOW' && readFixture) {
      output = await readFixture();
      await d2guardApi.ingestEvent({...event, event_id: crypto.randomUUID(), stage: 'TOOL_POST_EXEC',
        event_type: 'TOOL_RETURN', source_type: 'LOCAL_FILE', source_uri: String(toolArgs.path), raw_content: output});
    }
    return {success: final === 'ALLOW', blocked: final === 'BLOCK', verdict: final,
      output, verdictResponse, error: final === 'BLOCK' ? verdictResponse.explainable_report : undefined};
  }
}
