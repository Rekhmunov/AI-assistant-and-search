import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { devActivatePro, deleteAccount, fetchMe, fetchSession } from "../api/client";
import { AuthGate } from "../components/AuthGate";
import { MobileNewThreadButton } from "../components/MobileNewThreadButton";
import { MobilePageHeader } from "../components/MobilePageHeader";
import { ProfileAccountSection } from "../components/ProfileAccountSection";
import { useDesktopLayout } from "../hooks/useDesktopLayout";
import { isMaxWebApp } from "../lib/maxApp";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

type ProfileTier = "pro" | "guest" | "free";

function getProfileTier(plan: string | undefined, isGuest: boolean): ProfileTier {
  if (plan === "pro") return "pro";
  if (isGuest) return "guest";
  return "free";
}

function getProfileTierLabel(tier: ProfileTier): string {
  if (tier === "pro") return "PRO";
  if (tier === "guest") return "GUEST";
  return "FREE";
}

export function Profile() {
  const token = useAuthStore((s) => s.token);
  const setUser = useAuthStore((s) => s.setUser);
  const clear = useAuthStore((s) => s.clear);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const inMax = isMaxWebApp();
  const isDesktop = useDesktopLayout();

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
  const profileTier = getProfileTier(user?.plan, Boolean(session?.is_guest));
  const profileTierLabel = getProfileTierLabel(profileTier);
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
    <div className={`page page-profile${isDesktop ? "" : " page-profile--mobile"}`}>
      {isDesktop ? (
        <header className="profile-page-header">
          <h1 className="mobile-page-title">{t("profile")}</h1>
        </header>
      ) : (
        <MobilePageHeader variant="profile" title={t("profile")} />
      )}

      <div className="profile-mobile-scroll">
      <div className="profile-hero">
        <div className={`profile-avatar profile-avatar--${profileTier}`} aria-label={profileTierLabel}>
          {profileTierLabel}
        </div>
        <div className="profile-hero-meta">
          <div className="profile-name">{name}</div>
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

      {!isDesktop && (
        <div className="mobile-new-thread-bar">
          <MobileNewThreadButton onClick={() => navigate("/")} />
        </div>
      )}
    </div>
  );
}
