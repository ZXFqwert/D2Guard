import { useEffect, useRef, ReactNode } from "react";
import { X, ArrowUpRight, ShieldCheck } from "lucide-react";
import { Verdict } from "../api/d2guardClient";

export function Logo({ large = false }: { large?: boolean }) {
  return (
    <svg
      className={large ? "brand-logo large" : "brand-logo"}
      viewBox="0 0 48 48"
      fill="none"
      aria-label="双镜 D²Guard 徽章"
    >
      <path
        d="M8 9 23 3 38 9v15c0 9-9 16-15 20C17 40 8 33 8 24Z"
        fill="#e0eee7"
        stroke="#26715b"
        strokeWidth="1.8"
      />
      <path
        d="m19 12 14-5 10 5v13c0 7-6 13-12 17-6-4-12-10-12-17Z"
        fill="#f5f7f1"
        stroke="#26715b"
        strokeWidth="1.8"
      />
      <path
        d="m19 12 12 13 12-13M31 25v17M8 9l15 16 15-16M23 25v19"
        stroke="#26715b"
        strokeWidth="1.3"
      />
      <path d="m23 3 10 4" stroke="#c39450" strokeWidth="2" />
    </svg>
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
      <svg className="armor-texture" width="100%" height="100%">
        <defs>
          <pattern
            id="armor-pattern"
            width="38"
            height="38"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M0 8 8 0M0 30 30 0M8 38 38 8M30 38 38 30"
              stroke="currentColor"
              strokeWidth=".7"
            />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#armor-pattern)" />
      </svg>
      {["tl", "tr", "bl", "br"].map((c) => (
        <svg key={c} className={`armor-corner ${c}`} viewBox="0 0 60 60">
          <path d="M3 56V17L17 3h39M11 44V21l10-10h23" />
          <path className="gold" d="M3 28 28 3M16 38V24l8-8h14" />
          <circle cx="22" cy="22" r="2" />
        </svg>
      ))}
      <div className="armor-nameplate">
        <ShieldCheck size={13} />
        <b>双镜铠甲护体中</b>
        <span>Hook + Gateway + Core 全链路接管</span>
        <ArrowUpRight size={12} />
      </div>
    </div>
  );
}
