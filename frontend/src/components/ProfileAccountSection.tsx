import { FormEvent, useState } from "react";
import { bindEmail, bindMax } from "../api/client";
import { getMaxBotUrl, getMaxInitData, isMaxWebApp } from "../lib/maxApp";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";
import type { UserProfile } from "../api/client";

interface Props {
  user: UserProfile;
  token: string;
  onUserUpdated: (user: UserProfile) => void;
}

export function ProfileAccountSection({ user, token, onUserUpdated }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [bindError, setBindError] = useState("");
  const [bindBusy, setBindBusy] = useState(false);
  const [maxBusy, setMaxBusy] = useState(false);

  const inMax = isMaxWebApp();
  const hasMax = Boolean(user.max_linked);
  const hasEmail = Boolean(user.email);

  const onBindEmail = async (e: FormEvent) => {
    e.preventDefault();
    setBindError("");
    setBindBusy(true);
    try {
      const updated = await bindEmail(token, email, password);
      onUserUpdated(updated);
      setEmail("");
      setPassword("");
    } catch (err) {
      setBindError(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setBindBusy(false);
    }
  };

  const onBindMaxInApp = async () => {
    const initData = getMaxInitData();
    if (!initData) return;
    setMaxBusy(true);
    setBindError("");
    try {
      const updated = await bindMax(token, initData);
      onUserUpdated(updated);
    } catch (err) {
      setBindError(err instanceof Error ? err.message : "Не удалось привязать MAX");
    } finally {
      setMaxBusy(false);
    }
  };

  return (
    <section className="profile-section">
      <h2 className="profile-section-title">{t("accountLinks")}</h2>

      <div className="profile-link-row">
        <span>MAX</span>
        <span className={hasMax ? "status-ok" : "status-muted"}>
          {hasMax ? t("maxLinked") : t("maxNotLinked")}
        </span>
      </div>

      {!hasMax && (
        <div className="profile-bind-block">
          {inMax ? (
            <button type="button" className="btn-primary btn-block" disabled={maxBusy} onClick={onBindMaxInApp}>
              {maxBusy ? "…" : t("linkMaxNow")}
            </button>
          ) : (
            <>
              <p className="hint">{t("openInMaxHint")}</p>
              <a href={getMaxBotUrl()} target="_blank" rel="noopener noreferrer" className="btn-primary btn-block">
                {t("openInMax")}
              </a>
            </>
          )}
        </div>
      )}

      <div className="profile-link-row" style={{ marginTop: 16 }}>
        <span>Email</span>
        <span className={hasEmail ? "status-ok" : "status-muted"}>
          {hasEmail ? user.email : t("emailNotSet")}
        </span>
      </div>

      {!hasEmail && hasMax && (
        <div className="profile-bind-block">
          <p className="hint">{t("addEmailHint")}</p>
          <form onSubmit={onBindEmail}>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
              />
            </label>
            <label>
              {t("passwordLabel")}
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
              />
            </label>
            {bindError && <p className="composer-error">{bindError}</p>}
            <button type="submit" className="btn-secondary btn-block" disabled={bindBusy}>
              {bindBusy ? "…" : t("addEmail")}
            </button>
          </form>
        </div>
      )}

      {!hasEmail && !hasMax && inMax && (
        <p className="hint">{t("maxOnlyNoEmailNeeded")}</p>
      )}

      {bindError && hasEmail && <p className="composer-error">{bindError}</p>}
    </section>
  );
}
