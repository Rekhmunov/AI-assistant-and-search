import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { devActivatePro, fetchMe, deleteAccount, fetchSession } from "../api/client";
import { ProfileAccountSection } from "../components/ProfileAccountSection";
import { isMaxWebApp } from "../lib/maxApp";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

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
      <div className="page">
        <h1>{t("profile")}</h1>
        <p className="auth-gate-text">
          {inMax ? t("profileMaxLoginHint") : t("profileLoginHint")}
        </p>
        {!inMax && (
          <Link to="/login" className="btn-primary btn-block">
            {t("signIn")}
          </Link>
        )}
        <Link to="/" className="btn-link" style={{ display: "block", marginTop: 16, textAlign: "center" }}>
          {t("backToSearch")}
        </Link>
      </div>
    );
  }

  const name = [user?.first_name, user?.last_name].filter(Boolean).join(" ") || "Пользователь";

  const activatePro = async () => {
    await devActivatePro(token);
    const updated = await fetchMe(token);
    setUser(updated);
    queryClient.invalidateQueries({ queryKey: ["me"] });
  };

  const onDelete = async () => {
    if (!confirm("Удалить аккаунт?")) return;
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
    <div className="page">
      <h1>{t("profile")}</h1>
      <div className="profile-limits-card">
        <span className="profile-limits-label">{t("searchesToday")}</span>
        <strong className="profile-limits-value">
          {searchesToday}/{searchesLimit}
        </strong>
        {session?.is_guest && (
          <p className="profile-limits-hint">{t("guestLimitsHint")}</p>
        )}
      </div>

      <div className="profile-card">
        <div>👤 {name}</div>
        <div style={{ marginTop: 4, color: "var(--muted)" }}>
          {t("plan")}: {user?.plan === "pro" ? "Pro" : "Free"}
        </div>
      </div>

      {user && <ProfileAccountSection user={user} token={token} onUserUpdated={onUserUpdated} />}

      {user?.plan !== "pro" && (
        <div className="pro-banner">
          <strong>{t("upgradePro")}</strong>
          <div>{t("proPrice")}</div>
          <div style={{ fontSize: "0.85rem", marginTop: 8 }}>{t("proBenefits")}</div>
          <button type="button" onClick={activatePro}>
            {t("upgradePro")}
          </button>
        </div>
      )}

      <div style={{ color: "var(--muted)" }}>
        {t("language")}: Русский
      </div>
      {user?.email && (
        <button
          type="button"
          className="btn-secondary btn-block"
          style={{ marginTop: 16 }}
          onClick={() => {
            clear();
            navigate(inMax ? "/" : "/login");
          }}
        >
          {t("signOut")}
        </button>
      )}
      {!user?.email && inMax && (
        <p className="hint" style={{ marginTop: 16 }}>
          {t("maxSignOutHint")}
        </p>
      )}
      <button type="button" className="danger-link" onClick={onDelete}>
        {t("deleteAccount")}
      </button>
    </div>
  );
}
