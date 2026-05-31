import { useState } from "react";
import type { Source } from "../api/client";
import { t } from "../i18n";

import { SourceLink } from "./SourceLink";

export function SourcesCollapsible({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false);
  if (!sources.length) return null;

  const preview = sources.slice(0, 4).map((s) => s.domain).join(" · ");

  return (
    <section className="sources-collapsible">
      <button
        type="button"
        className="sources-collapsible-trigger"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="sources-collapsible-label">
          {t("sourcesCount", { n: sources.length })}
        </span>
        <span className="sources-collapsible-preview">{preview}</span>
        <span className="sources-collapsible-chevron" aria-hidden>
          {open ? "▲" : "▼"}
        </span>
      </button>
      {open && (
        <ul className="sources-compact-list">
          {sources.map((s) => (
            <li key={s.index}>
              <SourceLink href={s.url} className="sources-compact-item">
                <span className="sources-compact-domain">[{s.index}] {s.domain}</span>
                <span className="sources-compact-title">{s.title}</span>
              </SourceLink>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
