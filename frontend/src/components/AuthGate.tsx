import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { t } from "../i18n";
import { AuthModalCard, AuthShell } from "./AuthModalCard";

type Props = {
  title: string;
  hint?: string;
  primaryTo?: string;
  primaryLabel?: string;
  primaryAction?: () => void | Promise<void>;
  primaryBusy?: boolean;
  showPrimary?: boolean;
  showSecondary?: boolean;
  showBrand?: boolean;
  icon?: ReactNode;
};

function ProfileGateIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M5 20c0-3.5 3.1-6 7-6s7 2.5 7 6"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function HistoryGateIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 8v5l3 2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M3.5 12a8.5 8.5 0 101.2-4.3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path
        d="M3 7v5h5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Экран «нужен вход» для профиля и истории. */
export function AuthGate({
  title,
  hint,
  primaryTo,
  primaryLabel,
  primaryAction,
  primaryBusy = false,
  showPrimary = true,
  showSecondary = true,
  showBrand = true,
  icon,
}: Props) {
  const gateIcon = icon === undefined && showBrand ? <ProfileGateIcon /> : icon;

  return (
    <div className="page page-auth-gate">
      <AuthShell>
        <AuthModalCard
          title={title}
          subtitle={hint}
          showBrand={showBrand}
          icon={gateIcon}
          footer={
            showSecondary ? (
              <Link to="/" className="auth-modal-link">
                {t("backToSearch")}
              </Link>
            ) : undefined
          }
        >
          {showPrimary && primaryLabel && (primaryAction || primaryTo) && (
            <div className="auth-modal-actions">
              {primaryAction ? (
                <button
                  type="button"
                  className="btn-primary btn-block"
                  disabled={primaryBusy}
                  onClick={() => void primaryAction()}
                >
                  {primaryBusy ? "…" : primaryLabel}
                </button>
              ) : (
                <Link to={primaryTo!} className="btn-primary btn-block">
                  {primaryLabel}
                </Link>
              )}
            </div>
          )}
        </AuthModalCard>
      </AuthShell>
    </div>
  );
}
