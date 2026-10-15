import { useEffect, useRef, ReactNode } from "react";
import { X, ShieldCheck } from "lucide-react";
import { Verdict } from "../api/d2guardClient";

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
          ? "双镜 D²Guard：快慢双镜与增量状态流全链路接管中"
          : "双镜 D²Guard：Codex 极简工作台模式"
      }
    >
      <svg
        className="d2-emblem-svg"
        viewBox="0 0 64 64"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="d2CoreGrad" x1="8" y1="8" x2="56" y2="56" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor={armor ? "#1e3a8a" : "#1f4d3d"} />
            <stop offset="55%" stopColor={armor ? "#2563eb" : "#2e6e56"} />
            <stop offset="100%" stopColor={armor ? "#06b6d4" : "#529478"} />
          </linearGradient>
          <linearGradient id="d2LensGrad" x1="16" y1="14" x2="48" y2="50" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor={armor ? "#38bdf8" : "#65a38c"} stopOpacity="0.95" />
            <stop offset="100%" stopColor={armor ? "#1d4ed8" : "#286b54"} stopOpacity="0.25" />
          </linearGradient>
        </defs>
        {/* Outer hexagonal armor chassis */}
        <polygon
          className="d2-emblem-chassis"
          points="32,3 57,17.5 57,46.5 32,61 7,46.5 7,17.5"
          fill="url(#d2CoreGrad)"
          fillOpacity={armor ? "0.14" : "0.08"}
          stroke="url(#d2CoreGrad)"
          strokeWidth={armor ? "2.4" : "1.6"}
        />
        {/* Corner armor lock brackets (highlighted in Dual-Mirror Armor mode) */}
        <path
          className="d2-emblem-armor-wing"
          d="M32 6 L53 18.2 M53 45.8 L32 58 M11 45.8 L11 18.2"
          stroke={armor ? "#0ea5e9" : "#7b9384"}
          strokeWidth={armor ? "2" : "1"}
          strokeLinecap="round"
          strokeDasharray={armor ? "6 3" : "2 4"}
          opacity={armor ? "0.95" : "0.4"}
        />
        {/* Mirror 1 (Fast Mirror / System 1 Lens - Left/Upper) */}
        <circle
          className="d2-emblem-lens lens-fast"
          cx="27"
          cy="29"
          r="12.5"
          fill="url(#d2LensGrad)"
          fillOpacity={armor ? "0.28" : "0.16"}
          stroke={armor ? "#0284c7" : "#2e6e56"}
          strokeWidth="2.1"
        />
        {/* Mirror 2 (Slow Mirror / System 2 Lens - Right/Lower intersecting) */}
        <circle
          className="d2-emblem-lens lens-slow"
          cx="37"
          cy="35"
          r="12.5"
          fill="url(#d2LensGrad)"
          fillOpacity={armor ? "0.34" : "0.18"}
          stroke={armor ? "#1d4ed8" : "#3b7a62"}
          strokeWidth="2.1"
        />
        {/* Incremental State Stream (D² trajectory wave through intersection) */}
        <path
          className="d2-emblem-stream"
          d="M14 32 C22 24, 29 40, 37 28 C42 21, 46 35, 50 32"
          stroke={armor ? "#06b6d4" : "#286b54"}
          strokeWidth="2.2"
          strokeLinecap="round"
        />
        {/* Center Core Anchor Point */}
        <circle
          cx="32"
          cy="32"
          r={armor ? "3.2" : "2.4"}
          fill={armor ? "#0ea5e9" : "#286b54"}
        />
      </svg>
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
      <div className="armor-rail armor-rail-top" />
      <div className="armor-rail armor-rail-bottom" />
      <div className="armor-rail armor-rail-left" />
      <div className="armor-rail armor-rail-right" />
      <div className="armor-corner armor-corner-tl" />
      <div className="armor-corner armor-corner-tr" />
      <div className="armor-corner armor-corner-bl" />
      <div className="armor-corner armor-corner-br" />
      <div className="armor-nameplate">
        <span className="armor-pulse-dot" aria-hidden="true" />
        <ShieldCheck size={14} aria-hidden="true" />
        <b>双镜铠甲护体中 · Hook + Gateway + Core 全链路接管</b>
        <span className="armor-subtag">D¹ Laya · D² StateFlow</span>
      </div>
    </div>
  );
}
