import { FormEvent, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { fetchLegalBySlug, fetchLegalRegisterMeta, loginEmail, registerEmail } from "../api/client";
import { AuthModalCard, AuthShell } from "../components/AuthModalCard";
import { LegalDocumentModal } from "../components/LegalDocumentModal";
import { t } from "../i18n";
import { isMaxWebApp } from "../lib/maxApp";
import { useAuthStore } from "../store/authStore";

type LegalModalSlug = "privacy" | "pd_consent" | null;

/** Вход по email — только для веб-сайта, не для миниаппа MAX. */
export function LoginPage() {
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);
  const setAuth = useAuthStore((s) => s.setAuth);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [acceptPrivacy, setAcceptPrivacy] = useState(false);
  const [acceptPdConsent, setAcceptPdConsent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [legalModalSlug, setLegalModalSlug] = useState<LegalModalSlug>(null);

  const inMax = isMaxWebApp();

  const { data: registerMeta } = useQuery({
    queryKey: ["legal-register-meta"],
    queryFn: fetchLegalRegisterMeta,
    staleTime: 60_000,
  });

  const privacyDoc = useMemo(
    () => registerMeta?.documents.find((d) => d.slug === "privacy"),
    [registerMeta],
  );
  const pdConsentDoc = useMemo(
    () => registerMeta?.documents.find((d) => d.slug === "pd_consent"),
    [registerMeta],
  );

  const { data: modalDoc, isLoading: modalLoading } = useQuery({
    queryKey: ["legal-modal", legalModalSlug],
    queryFn: () => fetchLegalBySlug(legalModalSlug!),
    enabled: legalModalSlug != null,
  });

  useEffect(() => {
    if (inMax && token) navigate("/profile", { replace: true });
  }, [inMax, token, navigate]);

  if (inMax) {
    return <Navigate to="/" replace />;
  }

  if (token) {
    return <Navigate to="/" replace />;
  }

  const canRegister =
    acceptPrivacy &&
    acceptPdConsent &&
    Boolean(privacyDoc?.version_id) &&
    Boolean(pdConsentDoc?.version_id);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (mode === "register" && !canRegister) {
      setError(t("registerConsentRequired"));
      return;
    }
    setBusy(true);
    try {
      const data =
        mode === "login"
          ? await loginEmail(email, password)
          : await registerEmail(email, password, firstName || undefined, {
              privacy_version_id: privacyDoc!.version_id,
              pd_consent_version_id: pdConsentDoc!.version_id,
            });
      setAuth(data.access_token, data.user);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loginError"));
    } finally {
      setBusy(false);
    }
  };

  const switchMode = (next: "login" | "register") => {
    setMode(next);
    setError("");
    setAcceptPrivacy(false);
    setAcceptPdConsent(false);
  };

  return (
    <div className="page page-login">
      <AuthShell>
        <AuthModalCard
          footer={
            <Link to="/" className="auth-modal-link">
              {t("continueAsGuest")}
            </Link>
          }
        >
          <div className="auth-mode-tabs" role="tablist" aria-label={t("loginModeTabs")}>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "login"}
              className={`auth-mode-tab${mode === "login" ? " auth-mode-tab--active" : ""}`}
              onClick={() => switchMode("login")}
            >
              {t("signIn")}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "register"}
              className={`auth-mode-tab${mode === "register" ? " auth-mode-tab--active" : ""}`}
              onClick={() => switchMode("register")}
            >
              {t("register")}
            </button>
          </div>

          <form className="auth-form" onSubmit={onSubmit}>
            {mode === "register" && (
              <label className="auth-field">
                <span className="auth-field-label">{t("firstName")}</span>
                <input
                  className="auth-field-input"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  autoComplete="given-name"
                  placeholder={t("firstNameOptional")}
                />
              </label>
            )}
            <label className="auth-field">
              <span className="auth-field-label">Email</span>
              <input
                className="auth-field-input"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="username"
                placeholder="name@example.com"
              />
            </label>
            <label className="auth-field">
              <span className="auth-field-label">
                {t("password")}
                {mode === "register" && (
                  <span className="auth-field-label-note"> ({t("passwordMinHint")})</span>
                )}
              </span>
              <input
                className="auth-field-input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={mode === "register" ? 8 : 1}
                autoComplete={mode === "login" ? "current-password" : "new-password"}
              />
            </label>

            {mode === "register" && (
              <div className="auth-consents">
                <label className="auth-consent-row">
                  <input
                    type="checkbox"
                    checked={acceptPdConsent}
                    onChange={(e) => setAcceptPdConsent(e.target.checked)}
                  />
                  <span>
                    {t("registerConsentPdPrefix")}
                    {"\u00A0"}
                    <span
                      role="button"
                      tabIndex={0}
                      className="auth-consent-link"
                      onClick={() => setLegalModalSlug("pd_consent")}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setLegalModalSlug("pd_consent");
                        }
                      }}
                    >
                      {t("registerConsentPdLink")}
                    </span>
                  </span>
                </label>
                <label className="auth-consent-row">
                  <input
                    type="checkbox"
                    checked={acceptPrivacy}
                    onChange={(e) => setAcceptPrivacy(e.target.checked)}
                  />
                  <span>
                    {t("registerConsentPrivacyPrefix")}
                    {"\u00A0"}
                    <span
                      role="button"
                      tabIndex={0}
                      className="auth-consent-link"
                      onClick={() => setLegalModalSlug("privacy")}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setLegalModalSlug("privacy");
                        }
                      }}
                    >
                      {t("registerConsentPrivacyLink")}
                    </span>
                  </span>
                </label>
              </div>
            )}

            {error && <p className="auth-modal-error">{error}</p>}
            <button
              type="submit"
              className="btn-primary btn-block"
              disabled={busy || (mode === "register" && !canRegister)}
            >
              {busy ? "…" : mode === "login" ? t("signIn") : t("createAccount")}
            </button>
          </form>
        </AuthModalCard>
      </AuthShell>

      {legalModalSlug && (
        <LegalDocumentModal
          title={modalDoc?.title ?? ""}
          contentHtml={modalDoc?.content_html ?? ""}
          loading={modalLoading}
          onClose={() => setLegalModalSlug(null)}
        />
      )}
    </div>
  );
}
