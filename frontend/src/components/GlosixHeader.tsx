import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchSession } from "../api/client";
import { isMaxWebApp } from "../lib/maxApp";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

interface Props {
  showLimits?: boolean;
}

export function GlosixHeader({ showLimits = true }: Props) {
  const token = useAuthStore((s) => s.token);
  const inMax = isMaxWebApp();

  const { data: session } = useQuery({
    queryKey: ["session", token],
    queryFn: () => fetchSession(token),
    enabled: showLimits,
  });

  const limits =
    session &&
    (session.authenticated || session.is_guest
      ? `${session.searches_today}/${session.searches_limit}`
      : null);

  return (
    <header className="glosix-header">
      <Link to="/" className="glosix-brand" aria-label="Glosix">
        <img src="/glosix-logo.svg" alt="Glosix" className="glosix-logo" />
      </Link>
      <div className="glosix-header-actions">
        {showLimits && limits && (
          <span className="limits-badge" title={session?.is_guest ? t("guestLimitsHint") : undefined}>
            {limits}
          </span>
        )}
        {!token && !inMax && (
          <Link to="/login" className="header-login-btn">
            {t("signIn")}
          </Link>
        )}
        {!token && inMax && (
          <Link to="/profile" className="header-login-btn">
            {t("navProfile")}
          </Link>
        )}
        {token && (
          <Link to="/profile" className="header-login-btn">
            {t("navProfile")}
          </Link>
        )}
      </div>
    </header>
  );
}
