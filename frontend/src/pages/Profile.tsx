import { useQuery, useQueryClient } from "@tanstack/react-query";
import { devActivatePro, fetchMe, deleteAccount } from "../api/client";
import { t } from "../i18n";
import { useAuthStore } from "../store/authStore";

export function Profile() {
  const token = useAuthStore((s) => s.token)!;
  const setUser = useAuthStore((s) => s.setUser);
  const clear = useAuthStore((s) => s.clear);
  const queryClient = useQueryClient();

  const { data: user } = useQuery({
    queryKey: ["me"],
    queryFn: () => fetchMe(token),
    enabled: !!token,
  });

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
  };

  return (
    <div className="page">
      <h1>{t("profile")}</h1>
      <div className="profile-card">
        <div>👤 {name}</div>
        <div style={{ marginTop: 8, color: "var(--muted)" }}>
          {t("plan")}: {user?.plan === "pro" ? "Pro" : "Free"}
        </div>
        <div style={{ marginTop: 4, color: "var(--muted)" }}>
          {t("searchesToday")}: {user?.searches_today ?? 0}/{user?.searches_limit ?? 10}
        </div>
      </div>

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
      <button type="button" className="danger-link" onClick={onDelete}>
        {t("deleteAccount")}
      </button>
    </div>
  );
}
