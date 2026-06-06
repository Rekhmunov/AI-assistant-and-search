import { useState, type ReactNode } from "react";

type Props = {
  title: string;
  subtitle?: string;
  badge?: string | number;
  defaultOpen?: boolean;
  children: ReactNode;
};

export function AuditCollapsibleSection({
  title,
  subtitle,
  badge,
  defaultOpen = false,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="audit-collapsible card">
      <button
        type="button"
        className={`audit-collapsible-toggle${open ? " audit-collapsible-toggle--open" : ""}`}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span
          className={`audit-collapsible-chevron${open ? " audit-collapsible-chevron--open" : ""}`}
          aria-hidden
        >
          ▶
        </span>
        <span className="audit-collapsible-heading">
          <span className="audit-collapsible-title">{title}</span>
          {subtitle ? <span className="audit-collapsible-sub">{subtitle}</span> : null}
        </span>
        {badge != null ? <span className="audit-collapsible-badge">{badge}</span> : null}
      </button>
      {open ? <div className="audit-collapsible-body">{children}</div> : null}
    </section>
  );
}
