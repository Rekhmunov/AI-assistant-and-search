import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { devActivatePro, deleteAccount, fetchMe, fetchSession } from "../api/client";
import { AuthGate } from "../components/AuthGate";
import { ProfileAccountSection } from "../components/ProfileAccountSection";
import { isMaxWebApp } from "../lib/maxApp";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase();
  }
  return (parts[0]?.slice(0, 2) ?? "?").toUpperCase();
}

export function Profile() {
  const token = useAuthStore((s) => s.token);
  const setUser = useAuthStore((s) => s.setUser);
  const clear = useAuthStore((s) => s.clear);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const inMax = isMaxWebApp();

  const { data: user } = useQuery({
    queryKey: ["me"],
    queryFn: () => fetchMe(token!),
    enabled: !!token,
  });

  const { data: session } = useQuery({
    queryKey: ["session", token],
    queryFn: () => fetchSession(token),
    enabled: !!token,
  });

  const searchesToday = session?.searches_today ?? user?.searches_today ?? 0;
  const searchesLimit = session?.searches_limit ?? user?.searches_limit ?? 10;

  if (!token) {
    return (
      <AuthGate
        title={t("profile")}
        hint={inMax ? t("profileMaxLoginHint") : t("profileLoginHint")}
        primaryTo="/login"
        primaryLabel={t("signIn")}
        showPrimary={!inMax}
        showSecondary
      />
    );
  }

  const name = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || t("profileDefaultName");
  const isPro = user?.plan === "pro";
  const usageRatio = searchesLimit > 0 ? Math.min(1, searchesToday / searchesLimit) : 0;
  const usagePercent = Math.round(usageRatio * 100);

  const activatePro = async () => {
    await devActivatePro(token);
    const updated = await fetchMe(token);
    setUser(updated);
    queryClient.invalidateQueries({ queryKey: ["me"] });
  };

  const onDelete = async () => {
    if (!confirm(t("deleteAccountConfirm"))) return;
    await deleteAccount(token);
    clear();
    navigate("/");
  };

  const onUserUpdated = (updated: typeof user) => {
    if (updated) setUser(updated);
    queryClient.invalidateQueries({ queryKey: ["me"] });
    queryClient.invalidateQueries({ queryKey: ["session"] });
  };

  return (
    <div className="page page-profile">
      <header className="profile-page-header">
        <h1 className="profile-page-title">{t("profile")}</h1>
      </header>

      <div className="profile-hero">
        <div className="profile-avatar" aria-hidden>
          {getInitials(name)}
        </div>
        <div className="profile-hero-meta">
          <div className="profile-name">{name}</div>
          <div className="profile-badges">
            <span className={`profile-plan-badge${isPro ? " profile-plan-badge--pro" : ""}`}>
              {isPro ? "Pro" : "Free"}
            </span>
            {session?.is_guest && <span className="profile-guest-badge">{t("profileGuestBadge")}</span>}
          </div>
        </div>
      </div>

      <section className="profile-card profile-stats-card">
        <div className="profile-stats-head">
          <span className="profile-stats-label">{t("searchesToday")}</span>
          <strong className="profile-stats-value">
            {searchesToday}
            <span className="profile-stats-limit">/{searchesLimit}</span>
          </strong>
        </div>
        <div
          className="profile-usage-bar"
          role="progressbar"
          aria-valuenow={searchesToday}
          aria-valuemin={0}
          aria-valuemax={searchesLimit}
          aria-label={t("searchesToday")}
        >
          <div
            className={`profile-usage-fill${usagePercent >= 90 ? " profile-usage-fill--high" : ""}`}
            style={{ width: `${usagePercent}%` }}
          />
        </div>
        {session?.is_guest && <p className="profile-hint">{t("guestLimitsHint")}</p>}
      </section>

      {user && <ProfileAccountSection user={user} token={token} onUserUpdated={onUserUpdated} />}

      {!isPro && (
        <section className="profile-card profile-pro-card">
          <div className="profile-pro-badge">Pro</div>
          <h2 className="profile-pro-title">{t("upgradePro")}</h2>
          <p className="profile-pro-price">{t("proPrice")}</p>
          <p className="profile-pro-benefits">{t("proBenefits")}</p>
          <button type="button" className="btn-primary btn-block" onClick={activatePro}>
            {t("upgradePro")}
          </button>
        </section>
      )}

      <section className="profile-card profile-settings-card">
        <div className="profile-settings-row">
          <span className="profile-settings-label">{t("language")}</span>
          <span className="profile-settings-value">{t("profileLanguageValue")}</span>
        </div>
      </section>

      <div className="profile-actions">
        {user?.email && (
          <button
            type="button"
            className="btn-secondary btn-block"
            onClick={() => {
              clear();
              navigate(inMax ? "/" : "/login");
            }}
          >
            {t("signOut")}
          </button>
        )}
        {!user?.email && inMax && <p className="profile-hint profile-hint--center">{t("maxSignOutHint")}</p>}
        <button type="button" className="btn-danger-ghost btn-block" onClick={onDelete}>
          {t("deleteAccount")}
        </button>
      </div>
    </div>
  );
}
