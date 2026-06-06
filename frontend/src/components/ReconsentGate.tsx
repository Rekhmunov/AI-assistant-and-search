import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  fetchConsentStatus,
  fetchLegalBySlug,
  fetchSession,
  recordLegalConsent,
  type PendingConsent,
} from "../api/client";
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
  const current: PendingConsent | undefined = pending[0];

  const { data: modalDoc, isLoading: modalLoading } = useQuery({
    queryKey: ["legal-reconsent-modal", docModalSlug],
    queryFn: () => fetchLegalBySlug(docModalSlug!),
    enabled: docModalSlug != null,
  });

  if (!token || session?.is_guest || !cookiesResolved || isLoading) return null;
  if (!current) return null;

  const accept = async () => {
    if (!checked || busy || !current) return;
    setBusy(true);
    setError("");
    try {
      await recordLegalConsent(token, {
        consents: [{ slug: current.slug, version_id: current.version_id }],
        source: "reconsent",
        consent_method: "checkbox",
      });
      setChecked(false);
      await queryClient.invalidateQueries({ queryKey: ["legal-consent-status", token] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить согласие");
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="reconsent-overlay" role="presentation">
        <div className="reconsent-modal app-modal" role="dialog" aria-modal="true">
          <h2 className="reconsent-title">Обновлён документ</h2>
          <p className="reconsent-text">
            Мы обновили «{current.title}». Чтобы продолжить пользоваться Glosix, подтвердите
            ознакомление с новой версией.
          </p>
          <label className="reconsent-check">
            <input type="checkbox" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
            <span>
              Я ознакомлен(а) с{" "}
              <button type="button" className="reconsent-link" onClick={() => setDocModalSlug(current.slug)}>
                {current.title.toLowerCase()}
              </button>
            </span>
          </label>
          {error && <p className="reconsent-error">{error}</p>}
          <button
            type="button"
            className="btn-primary btn-block"
            disabled={!checked || busy}
            onClick={() => void accept()}
          >
            {busy ? "…" : "Принять"}
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
