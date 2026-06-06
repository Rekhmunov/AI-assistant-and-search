import { FormEvent, useEffect, useState } from "react";
import { bindEmail, bindMax, changePassword, startBindMax } from "../api/client";
import type { UserProfile } from "../api/client";
import {
  buildMaxDeepLink,
  getMaxInitData,
  isMaxWebApp,
  takeMaxBindError,
} from "../lib/maxApp";
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
  const [bindInfo, setBindInfo] = useState("");
  const [bindBusy, setBindBusy] = useState(false);
  const [maxBusy, setMaxBusy] = useState(false);
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordBusy, setPasswordBusy] = useState(false);

  const inMax = isMaxWebApp();
  const hasMax = Boolean(user.max_linked);
  const hasEmail = Boolean(user.email);

  useEffect(() => {
    const pending = takeMaxBindError();
    if (pending) setBindError(pending);
  }, []);

  const onBindEmail = async (e: FormEvent) => {
    e.preventDefault();
    setBindError("");
    setBindInfo("");
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
    setBindInfo("");
    try {
      const updated = await bindMax(token, initData);
      onUserUpdated(updated);
    } catch (err) {
      setBindError(err instanceof Error ? err.message : t("profileMaxBindError"));
    } finally {
      setMaxBusy(false);
    }
  };

  const onChangePassword = async (e: FormEvent) => {
    e.preventDefault();
    setBindError("");
    setBindInfo("");
    if (newPassword !== confirmPassword) {
      setBindError(t("passwordMismatch"));
      return;
    }
    setPasswordBusy(true);
    try {
      await changePassword(token, currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setShowChangePassword(false);
      setBindInfo(t("passwordChanged"));
    } catch (err) {
      setBindError(err instanceof Error ? err.message : t("profileBindError"));
    } finally {
      setPasswordBusy(false);
    }
  };

  const onOpenMaxForBind = async () => {
    setBindError("");
    setBindInfo("");
    setMaxBusy(true);
    try {
      const { bind_token: bindToken } = await startBindMax(token);
      setBindInfo(t("openInMaxPending"));
      window.location.assign(buildMaxDeepLink(`bind_${bindToken}`));
    } catch (err) {
      setBindError(err instanceof Error ? err.message : t("profileMaxBindError"));
    } finally {
      setMaxBusy(false);
    }
  };

  return (
    <section className="profile-card profile-account-card">
      <div className="profile-link-item">
        <div className="profile-link-main">
          <span className="profile-link-label">MAX</span>
          <StatusBadge
            active={hasMax}
            activeLabel={
              user.max_user_id != null ? String(user.max_user_id) : t("maxLinked")
            }
            inactiveLabel={t("maxNotLinked")}
          />
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
                <button
                  type="button"
                  className="btn-primary btn-block"
                  disabled={maxBusy}
                  onClick={() => void onOpenMaxForBind()}
                >
                  {maxBusy ? "…" : t("openInMax")}
                </button>
              </>
            )}
            {bindInfo && <p className="profile-hint profile-hint--ok">{bindInfo}</p>}
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
        {hasEmail && !showChangePassword && (
          <button
            type="button"
            className="profile-email-action"
            onClick={() => {
              setShowChangePassword(true);
              setBindError("");
              setBindInfo("");
            }}
          >
            {t("changePassword")}
          </button>
        )}
        {hasEmail && showChangePassword && (
          <div className="profile-bind-block profile-bind-block--password">
            <form className="profile-bind-form" onSubmit={onChangePassword}>
                <label className="auth-field">
                  <span className="auth-field-label">{t("currentPassword")}</span>
                  <input
                    className="auth-field-input"
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                  />
                </label>
                <label className="auth-field">
                  <span className="auth-field-label">{t("newPassword")}</span>
                  <input
                    className="auth-field-input"
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    minLength={8}
                    autoComplete="new-password"
                  />
                </label>
                <label className="auth-field">
                  <span className="auth-field-label">{t("confirmPassword")}</span>
                  <input
                    className="auth-field-input"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    required
                    minLength={8}
                    autoComplete="new-password"
                  />
                </label>
                <div className="profile-bind-form-actions">
                  <button type="submit" className="btn-primary btn-block" disabled={passwordBusy}>
                    {passwordBusy ? "…" : t("savePassword")}
                  </button>
                  <button
                    type="button"
                    className="btn-secondary btn-block"
                    disabled={passwordBusy}
                    onClick={() => {
                      setShowChangePassword(false);
                      setCurrentPassword("");
                      setNewPassword("");
                      setConfirmPassword("");
                    }}
                  >
                    {t("cancel")}
                  </button>
                </div>
            </form>
          </div>
        )}
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
