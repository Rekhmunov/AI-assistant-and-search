import { FormEvent, useState } from "react";
import { bindEmail, bindMax } from "../api/client";
import type { UserProfile } from "../api/client";
import { getMaxBotUrl, getMaxInitData, isMaxWebApp } from "../lib/maxApp";
import { t } from "../i18n";

interface Props {
  user: UserProfile;
  token: string;
  onUserUpdated: (user: UserProfile) => void;
}

function StatusBadge({ active, activeLabel, inactiveLabel }: { active: boolean; activeLabel: string; inactiveLabel: string }) {
  return (
    <span className={`profile-status-badge${active ? " profile-status-badge--ok" : ""}`}>
      {active ? activeLabel : inactiveLabel}
    </span>
  );
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
      setBindError(err instanceof Error ? err.message : t("profileBindError"));
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
      setBindError(err instanceof Error ? err.message : t("profileMaxBindError"));
    } finally {
      setMaxBusy(false);
    }
  };

  return (
    <section className="profile-card">
      <h2 className="profile-card-title">{t("accountLinks")}</h2>

      <div className="profile-link-item">
        <div className="profile-link-main">
          <span className="profile-link-label">MAX</span>
          <StatusBadge active={hasMax} activeLabel={t("maxLinked")} inactiveLabel={t("maxNotLinked")} />
        </div>
        {!hasMax && (
          <div className="profile-bind-block">
            {inMax ? (
              <button type="button" className="btn-primary btn-block" disabled={maxBusy} onClick={onBindMaxInApp}>
                {maxBusy ? "…" : t("linkMaxNow")}
              </button>
            ) : (
              <>
                <p className="profile-hint">{t("openInMaxHint")}</p>
                <a
                  href={getMaxBotUrl()}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-primary btn-block"
                >
                  {t("openInMax")}
                </a>
              </>
            )}
          </div>
        )}
      </div>

      <div className="profile-link-item">
        <div className="profile-link-main">
          <span className="profile-link-label">Email</span>
          <StatusBadge
            active={hasEmail}
            activeLabel={user.email ?? t("emailNotSet")}
            inactiveLabel={t("emailNotSet")}
          />
        </div>
        {!hasEmail && hasMax && (
          <div className="profile-bind-block">
            <p className="profile-hint">{t("addEmailHint")}</p>
            <form className="profile-bind-form" onSubmit={onBindEmail}>
              <label className="auth-field">
                <span className="auth-field-label">Email</span>
                <input
                  className="auth-field-input"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  placeholder="name@example.com"
                />
              </label>
              <label className="auth-field">
                <span className="auth-field-label">{t("passwordLabel")}</span>
                <input
                  className="auth-field-input"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  autoComplete="new-password"
                />
              </label>
              <button type="submit" className="btn-secondary btn-block" disabled={bindBusy}>
                {bindBusy ? "…" : t("addEmail")}
              </button>
            </form>
          </div>
        )}
      </div>

      {!hasEmail && !hasMax && inMax && <p className="profile-hint">{t("maxOnlyNoEmailNeeded")}</p>}

      {bindError && <p className="auth-modal-error">{bindError}</p>}
    </section>
  );
}
