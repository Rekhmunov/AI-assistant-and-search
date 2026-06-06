import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";
import { RichTextEditor } from "../components/RichTextEditor";

type LegalVersion = {
  id: string;
  version_number: number;
  content_html: string;
  created_at: string;
  admin_email: string | null;
};

type LegalDocument = {
  slug: string;
  title: string;
  public_path: string;
  current_version: LegalVersion | null;
  versions: LegalVersion[];
};

const SLUG_LABELS: Record<string, string> = {
  privacy: "Политика конфиденциальности",
  pd_consent: "Согласие на обработку персональных данных",
  cookies: "Куки",
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ru-RU");
  } catch {
    return iso;
  }
}

function SectionChevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`settings-chevron${expanded ? " settings-chevron--expanded" : ""}`}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function DocumentSection({
  doc,
  canWrite,
  onSaved,
}: {
  doc: LegalDocument;
  canWrite: boolean;
  onSaved: (updated: LegalDocument) => void;
}) {
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState(doc.current_version?.content_html ?? "<p></p>");
  const [publicPath, setPublicPath] = useState(doc.public_path);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [previewVersionId, setPreviewVersionId] = useState<string | null>(null);

  useEffect(() => {
    setContent(doc.current_version?.content_html ?? "<p></p>");
    setPublicPath(doc.public_path);
    setPreviewVersionId(null);
  }, [doc]);

  const previewHtml =
    previewVersionId != null
      ? doc.versions.find((v) => v.id === previewVersionId)?.content_html
      : content;

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!canWrite) return;
    setBusy(true);
    setMsg("");
    try {
      const updated = await apiFetch<LegalDocument>(`/api/admin/legal/${doc.slug}`, {
        method: "PUT",
        body: JSON.stringify({ content_html: content, public_path: publicPath }),
      });
      onSaved(updated);
      setMsg("Сохранено — создана новая версия");
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Ошибка сохранения");
    } finally {
      setBusy(false);
    }
  };

  const label = SLUG_LABELS[doc.slug] ?? doc.title;

  return (
    <section className="settings-section settings-section--collapsible">
      <button
        type="button"
        className="settings-section-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="settings-section-toggle-label">{label}</span>
        <SectionChevron expanded={open} />
      </button>
      {open && (
        <div className="settings-section-panel documents-panel">
          <form onSubmit={save}>
            <label className="documents-field">
              Публичный URL
              <input
                type="text"
                value={publicPath}
                onChange={(e) => setPublicPath(e.target.value)}
                disabled={!canWrite}
                placeholder="/privacy"
              />
              <span className="documents-field-hint">
                Адрес на сайте (можно изменить). По умолчанию: {doc.public_path}
              </span>
            </label>

            <div className="documents-editor-wrap">
              <span className="documents-field-label">Текст документа</span>
              <RichTextEditor value={content} onChange={setContent} disabled={!canWrite} />
            </div>

            {previewHtml && (
              <div className="documents-preview">
                <h4 className="documents-preview-title">Предпросмотр</h4>
                <div
                  className="documents-preview-body legal-doc-html"
                  dangerouslySetInnerHTML={{ __html: previewHtml }}
                />
              </div>
            )}

            {canWrite && (
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy ? "Сохранение…" : "Сохранить новую версию"}
              </button>
            )}
            {msg && <p className="documents-msg">{msg}</p>}
          </form>

          {doc.versions.length > 0 && (
            <div className="documents-history">
              <h4 className="documents-history-title">История версий</h4>
              <ul className="documents-history-list">
                {doc.versions.map((v) => (
                  <li key={v.id} className="documents-history-item">
                    <button
                      type="button"
                      className={`documents-history-btn${
                        previewVersionId === v.id ? " documents-history-btn--active" : ""
                      }`}
                      onClick={() =>
                        setPreviewVersionId((cur) => (cur === v.id ? null : v.id))
                      }
                    >
                      <span>
                        v{v.version_number}
                        {doc.current_version?.id === v.id ? " (актуальная)" : ""}
                      </span>
                      <span className="documents-history-meta">
                        {formatDate(v.created_at)}
                        {v.admin_email ? ` · ${v.admin_email}` : ""}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export function DocumentsPage() {
  const { can } = useAuth();
  const [docs, setDocs] = useState<LegalDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const canWrite = can("legal:write");

  const load = useCallback(() => {
    setLoading(true);
    apiFetch<LegalDocument[]>("/api/admin/legal")
      .then(setDocs)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const onSaved = (updated: LegalDocument) => {
    setDocs((prev) => prev.map((d) => (d.slug === updated.slug ? updated : d)));
  };

  if (!can("legal:read")) {
    return <p>Нет доступа</p>;
  }

  return (
    <div className="settings-page documents-page">
      <h1>Документы</h1>
      <p className="documents-page-sub">
        Политика конфиденциальности, согласие на обработку ПДн и cookie. Каждое сохранение создаёт
        новую версию.
      </p>
      {loading && <p>Загрузка…</p>}
      {!loading && (
        <div className="card settings-form">
          {docs.map((doc) => (
            <DocumentSection key={doc.slug} doc={doc} canWrite={canWrite} onSaved={onSaved} />
          ))}
        </div>
      )}
    </div>
  );
}
