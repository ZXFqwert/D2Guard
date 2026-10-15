import { useEffect, useRef, ReactNode } from "react";
import { X, ShieldCheck } from "lucide-react";
import { Verdict } from "../api/d2guardClient";
import agentNormal from "../assets/guardian/agent-normal.png";
import agentProtected from "../assets/guardian/agent-protected.png";

export function Logo({
  large = false,
  armor = false,
}: {
  large?: boolean;
  armor?: boolean;
}) {
  return (
    <span
      className={`brand-logo guardian-logo${large ? " large" : ""}${armor ? " is-protected" : ""}`}
      role="img"
      aria-label={
        armor
          ? "双镜 D²Guard：动漫猫盾与快慢双镜全链路护体中"
          : "Codex Agent：无防护正常在线模式"
      }
    >
      <svg
        className="guardian-optical-ring"
        viewBox="0 0 64 64"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="d2OpticalRing" x1="6" y1="6" x2="58" y2="58" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#38bdf8" />
            <stop offset="50%" stopColor="#2563eb" />
            <stop offset="100%" stopColor="#fbbf24" />
          </linearGradient>
        </defs>
        <circle
          cx="32"
          cy="32"
          r="29"
          stroke="url(#d2OpticalRing)"
          strokeWidth="1.8"
          strokeDasharray="8 4"
          opacity={armor ? "0.9" : "0"}
        />
        <polygon
          points="32,2 58,17 58,47 32,62 6,47 6,17"
          stroke="url(#d2OpticalRing)"
          strokeWidth="1.3"
          opacity={armor ? "0.65" : "0"}
        />
      </svg>
      <img
        className="guardian-agent guardian-agent-normal"
        src={agentNormal}
        alt=""
        draggable={false}
      />
      <img
        className="guardian-agent guardian-agent-protected"
        src={agentProtected}
        alt=""
        draggable={false}
      />
    </span>
  );
}
export function Badge({ value }: { value: Verdict }) {
  return (
    <span className={`badge ${value.toLowerCase()}`}>
      {value === "ALLOW" ? "✓" : value === "BLOCK" ? "⊘" : "◷"} {value}
    </span>
  );
}
export function Empty({
  title,
  detail,
  children,
}: {
  title: string;
  detail?: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <ShieldCheck size={28} />
      <h3>{title}</h3>
      <p>{detail}</p>
      {children}
    </div>
  );
}
export function PageHeading({
  eyebrow,
  title,
  detail,
  children,
}: {
  eyebrow: string;
  title: string;
  detail: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{detail}</p>
      </div>
      <div className="heading-actions">{children}</div>
    </div>
  );
}
export function Panel({
  title,
  subtitle,
  children,
  action,
  className = "",
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-head">
        <div>
          <h3>{title}</h3>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Report({ text }: { text: string }) {
  const parts = text
    .replace(/ -> /g, "\n")
    .split(
      /(?=用户原始任务意图[：:]|实际违规动作(?:\/待审动作)?[：:]|污染源定位[：:]|判定结论[：:])/,
    )
    .filter(Boolean);
  return (
    <div className="report">
      {parts.map((p, i) => {
        const cut = p.search(/[：:]/);
        return (
          <div key={i}>
            {cut >= 0 && cut < 18 ? (
              <>
                <strong>{p.slice(0, cut)}</strong>
                <p>{p.slice(cut + 1)}</p>
              </>
            ) : (
              <p>{p}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
export function Modal({
  title,
  onClose,
  children,
  wide = false,
  drawer = false,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
  drawer?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const el = ref.current!;
    const focusable = () =>
      Array.from(
        el.querySelectorAll<HTMLElement>(
          'button:not(:disabled),input,select,textarea,a[href],[tabindex="0"]',
        ),
      ).filter((e) => e.offsetParent !== null);
    (focusable()[0] || el).focus();
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
      if (event.key === "Tab") {
        const items = focusable();
        const first = items[0],
          last = items.at(-1);
        if (!first) {
          event.preventDefault();
          return;
        }
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    el.addEventListener("keydown", handler);
    return () => {
      el.removeEventListener("keydown", handler);
      previous?.focus();
    };
  }, []);
  return (
    <div
      className={`overlay ${drawer ? "drawer-overlay" : ""}`}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        tabIndex={-1}
        className={`modal ${wide ? "wide" : ""} ${drawer ? "drawer" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="icon-button" onClick={onClose} aria-label="关闭">
            <X size={18} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}
export function ArmorFrame() {
  return (
    <div
      className="armor-frame"
      data-testid="armor-frame"
      aria-label="双镜铠甲护体中"
    >
      <div className="armor-nameplate">
        <img
          src={agentProtected}
          className="armor-crest-img"
          alt=""
          aria-hidden="true"
          draggable={false}
        />
        <span className="armor-pulse-dot" aria-hidden="true" />
        <ShieldCheck size={14} aria-hidden="true" />
        <b>双镜 D²Guard 防护已开启</b>
        <span className="armor-subtag">Hook + Gateway + D¹/D² 内核闭环</span>
      </div>
    </div>
  );
}
