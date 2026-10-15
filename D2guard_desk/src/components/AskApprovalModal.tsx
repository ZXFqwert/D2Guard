import { useEffect, useState } from "react";
import { Clock, ShieldAlert } from "lucide-react";
import { AskApprovalContext } from "../core/D2GuardHook";
import { Badge, Modal, Report } from "../desk/ui";
import { ms } from "../desk/types";
export function AskApprovalModal({
  context,
  onClose,
}: {
  context: AskApprovalContext | null;
  onClose: () => void;
}) {
  const [remaining, setRemaining] = useState(60);
  useEffect(() => {
    if (!context) return;
    const deadline = Date.now() + 60000;
    const timer = setInterval(() => {
      const n = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
      setRemaining(n);
      if (!n) {
        clearInterval(timer);
        context.resolve(false);
        onClose();
      }
    }, 250);
    return () => clearInterval(timer);
  }, [context]);
  if (!context) return null;
  const decide = (approved: boolean) => {
    context.resolve(approved);
    onClose();
  };
  return (
    <Modal title="需要你的单次授权" onClose={() => decide(false)} wide>
      <div className="ask-intro">
        <div className="ask-icon">
          <ShieldAlert size={26} />
        </div>
        <div>
          <Badge value="ASK" />
          <h3>此动作超出了当前安全边界</h3>
          <p>Agent 已挂起。请检视证据，决定是否批准本次工具申请。</p>
        </div>
        <div className="countdown">
          <Clock size={16} />
          <strong>{remaining}s</strong>
          <small>超时自动拒绝</small>
        </div>
      </div>
      <div className="progress-track amber">
        <span style={{ width: `${(remaining / 60) * 100}%` }} />
      </div>
      <Report text={context.verdictResponse.explainable_report} />
      <div className="row-between">
        <h4>{context.toolName}</h4>
        <small>
          快镜实测 {ms(context.verdictResponse.fast_mirror_label.latency_ms)}
        </small>
      </div>
      <pre>{JSON.stringify(context.toolArgs, null, 2)}</pre>
      <p className="small muted">
        授权仅绑定当前会话与本次调用。关闭弹窗视为拒绝。
      </p>
      <div className="modal-actions">
        <button className="danger" onClick={() => decide(false)}>
          拒绝并阻断
        </button>
        <button className="primary" onClick={() => decide(true)}>
          批准本次动作
        </button>
      </div>
    </Modal>
  );
}
