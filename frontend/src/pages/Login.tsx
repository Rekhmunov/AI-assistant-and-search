import { FormEvent, useEffect, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { loginEmail, registerEmail } from "../api/client";
import { AuthModalCard, AuthShell } from "../components/AuthModalCard";
import { t } from "../i18n";
import { isMaxWebApp } from "../lib/maxApp";
import { useAuthStore } from "../store/authStore";

/** Вход по email — только для веб-сайта, не для миниаппа MAX. */
export function LoginPage() {
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);
  const setAuth = useAuthStore((s) => s.setAuth);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const inMax = isMaxWebApp();

  useEffect(() => {
    if (inMax && token) navigate("/profile", { replace: true });
  }, [inMax, token, navigate]);

  if (inMax) {
    return <Navigate to="/" replace />;
  }

  if (token) {
    return <Navigate to="/" replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const data =
        mode === "login"
          ? await loginEmail(email, password)
          : await registerEmail(email, password, firstName || undefined);
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
            {error && <p className="auth-modal-error">{error}</p>}
            <button type="submit" className="btn-primary btn-block" disabled={busy}>
              {busy ? "…" : mode === "login" ? t("signIn") : t("createAccount")}
            </button>
          </form>
        </AuthModalCard>
      </AuthShell>
    </div>
  );
}
