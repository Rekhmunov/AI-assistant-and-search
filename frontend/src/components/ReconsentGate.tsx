import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  fetchConsentStatus,
  fetchLegalBySlug,
  fetchSession,
  recordLegalConsent,
} from "../api/client";
import { t } from "../i18n";
import { LegalDocumentModal } from "./LegalDocumentModal";
import { useAuthStore } from "../store/authStore";

export function ReconsentGate({ cookiesResolved }: { cookiesResolved: boolean }) {
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [docModalSlug, setDocModalSlug] = useState<string | null>(null);
  const [error, setError] = useState("");

  const { data: session } = useQuery({
    queryKey: ["session", token],
    queryFn: () => fetchSession(token),
    enabled: Boolean(token),
    staleTime: 30_000,
  });

  const { data: status, isLoading } = useQuery({
    queryKey: ["legal-consent-status", token],
    queryFn: () => fetchConsentStatus(token!),
    enabled: Boolean(token) && Boolean(session) && !session?.is_guest && cookiesResolved,
    staleTime: 0,
    refetchOnMount: "always",
  });

  const pending = status?.pending ?? [];

  const { data: modalDoc, isLoading: modalLoading } = useQuery({
    queryKey: ["legal-reconsent-modal", docModalSlug],
    queryFn: () => fetchLegalBySlug(docModalSlug!),
    enabled: docModalSlug != null,
  });

  if (!token || session?.is_guest || !cookiesResolved || isLoading) return null;
  if (!pending.length) return null;

  const accept = async () => {
    if (!checked || busy || !pending.length) return;
    setBusy(true);
    setError("");
    try {
      await recordLegalConsent(token, {
        consents: pending.map((item) => ({
          slug: item.slug,
          version_id: item.version_id,
        })),
        source: "reconsent",
        consent_method: "checkbox",
      });
      setChecked(false);
      await queryClient.invalidateQueries({ queryKey: ["legal-consent-status", token] });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("reconsentSaveError"));
    } finally {
      setBusy(false);
    }
  };

  const title =
    pending.length === 1 ? t("reconsentTitleSingle") : t("reconsentTitleMultiple");

  const introText =
    pending.length === 1
      ? t("reconsentTextSingle", { title: pending[0].title })
      : t("reconsentTextMultiple");

  return (
    <>
      <div className="reconsent-overlay" role="presentation">
        <div className="reconsent-modal app-modal" role="dialog" aria-modal="true">
          <h2 className="reconsent-title">{title}</h2>
          <p className="reconsent-text">{introText}</p>
          <ul className="reconsent-doc-list">
            {pending.map((item) => (
              <li key={item.slug}>
                <button
                  type="button"
                  className="reconsent-link"
                  onClick={() => setDocModalSlug(item.slug)}
                >
                  {item.title}
                </button>
              </li>
            ))}
          </ul>
          <label className="reconsent-check">
            <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
            <span>{t("reconsentCheckbox")}</span>
          </label>
          {error && <p className="reconsent-error">{error}</p>}
          <button
            type="button"
            className="btn-primary btn-block"
            disabled={!checked || busy}
            onClick={() => void accept()}
          >
            {busy ? "…" : t("reconsentAccept")}
          </button>
        </div>
      </div>

      {docModalSlug && (
        <LegalDocumentModal
          title={modalDoc?.title ?? ""}
          contentHtml={modalDoc?.content_html ?? ""}
          loading={modalLoading}
          onClose={() => setDocModalSlug(null)}
        />
      )}
    </>
  );
}
