import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  confirmProPayment,
  createProPayment,
  createSupportTicket,
  devActivatePro,
  deleteAccount,
  fetchAppConfig,
  fetchLegalBySlug,
  fetchMe,
  fetchMySupportTickets,
  fetchSession,
} from "../api/client";
import { AuthGate } from "../components/AuthGate";
import { LegalDocumentModal } from "../components/LegalDocumentModal";
import { MobileNewThreadButton } from "../components/MobileNewThreadButton";
import { MobilePageHeader } from "../components/MobilePageHeader";
import { ProPurchaseBlockedModal } from "../components/ProPurchaseBlockedModal";
import { ProPaymentStatusModal, type ProPaymentModalState } from "../components/ProPaymentStatusModal";
import { SupportFormModal } from "../components/SupportFormModal";
import { SupportToast } from "../components/SupportToast";
import { ProfileAccountSection } from "../components/ProfileAccountSection";
import { useDesktopLayout } from "../hooks/useDesktopLayout";
import { useSignOut } from "../hooks/useSignOut";
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

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

export function Profile() {
  const token = useAuthStore((s) => s.token);
  const setUser = useAuthStore((s) => s.setUser);
  const signOut = useSignOut();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const confirmInFlight = useRef(false);
  const [proBlockedOpen, setProBlockedOpen] = useState(false);
  const [paymentModal, setPaymentModal] = useState<ProPaymentModalState>({ open: false });
  const [acceptOffer, setAcceptOffer] = useState(false);
  const [offerModalOpen, setOfferModalOpen] = useState(false);
  const [supportModalOpen, setSupportModalOpen] = useState(false);
  const [supportSource, setSupportSource] = useState<"general" | "pro_payment">("general");
  const [supportToast, setSupportToast] = useState(false);
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

  const storeUser = useAuthStore((s) => s.user);
  const profileUser = user ?? storeUser;

  const { data: appConfig } = useQuery({
    queryKey: ["appConfig"],
    queryFn: fetchAppConfig,
    staleTime: 0,
    refetchOnMount: "always",
  });

  const { data: supportTickets, refetch: refetchSupportTickets } = useQuery({
    queryKey: ["support-tickets", token],
    queryFn: () => fetchMySupportTickets(token!),
    enabled: !!token && !session?.is_guest,
    staleTime: 30_000,
  });

  const ticketsWithReplies = (supportTickets ?? []).filter((ticket) => ticket.replies.length > 0);

  const profilePlan = profileUser?.plan;
  const needsOfferForPro = !!token && profilePlan !== "pro";

  const {
    data: offerDoc,
    isLoading: offerLoading,
    isError: offerLoadError,
    isFetched: offerFetched,
  } = useQuery({
    queryKey: ["legal-offer"],
    queryFn: () => fetchLegalBySlug("offer"),
    enabled: needsOfferForPro,
    staleTime: 60_000,
    retry: 1,
  });

  const offerVersionId = offerDoc?.version_id;

  const searchesToday = session?.searches_today ?? profileUser?.searches_today ?? 0;
  const searchesLimit = session?.searches_limit ?? profileUser?.searches_limit ?? 10;
  const proPriceRub = appConfig?.pro_price_rub ?? profileUser?.pro_price_rub ?? session?.pro_price_rub ?? 299;
  const proPurchaseDisabled = Boolean(appConfig?.pro_purchase_disabled);

  const refreshUserAfterPro = async () => {
    const updated = await fetchMe(token!);
    setUser(updated);
    queryClient.setQueryData(["me"], updated);
    queryClient.invalidateQueries({ queryKey: ["me"] });
    queryClient.invalidateQueries({ queryKey: ["session"] });
    return updated;
  };

  const runPaymentConfirm = async (options?: { retries?: number }) => {
    if (!token || confirmInFlight.current) return;
    confirmInFlight.current = true;
    setPaymentModal({ open: true, kind: "loading" });

    const retries = options?.retries ?? 3;
    try {
      for (let attempt = 0; attempt < retries; attempt += 1) {
        const result = await confirmProPayment(token);
        if (result.ok && result.plan === "pro") {
          await refreshUserAfterPro();
          setPaymentModal({ open: true, kind: "success" });
          return;
        }
        if (result.ok && result.plan !== "pro") {
          setPaymentModal({
            open: true,
            kind: "error",
            message: "Оплата найдена, но тариф не обновился. Обновите страницу или напишите в поддержку.",
            canRetry: true,
          });
          return;
        }

        const isPending =
          result.status === "pending" ||
          result.status === "waiting_for_capture" ||
          Boolean(result.message?.includes("обрабатывается"));

        if (isPending && attempt < retries - 1) {
          await sleep(2000);
          continue;
        }

        const paymentNotFound =
          !isPending &&
          Boolean(
            result.message?.includes("Успешная оплата не найдена") ||
              result.message?.includes("Оплата не завершена"),
          );

        setPaymentModal({
          open: true,
          kind: isPending ? "pending" : "error",
          message:
            result.message ||
            (isPending
              ? t("proPaymentPendingHint")
              : t("proPaymentNotFoundPrefix")),
          canRetry: !paymentNotFound,
          showSupportLink: paymentNotFound,
        });
        return;
      }
    } catch (err) {
      setPaymentModal({
        open: true,
        kind: "error",
        message: err instanceof Error ? err.message : "Не удалось активировать Pro",
        canRetry: true,
      });
    } finally {
      confirmInFlight.current = false;
    }
  };

  useEffect(() => {
    if (!token || searchParams.get("payment") !== "success") return;
    setSearchParams({}, { replace: true });
    void runPaymentConfirm({ retries: 4 });
  }, [token, searchParams, setSearchParams]);

  if (!token) {
    return (
      <AuthGate
        title={t("profileGuestGateTitle")}
        primaryTo="/login"
        primaryLabel={t("signIn")}
        showPrimary={!inMax}
        showSecondary
        showBrand={false}
      />
    );
  }

  const name = [profileUser?.first_name, profileUser?.last_name].filter(Boolean).join(" ") || t("profileDefaultName");
  const isPro = profileUser?.plan === "pro";
  const profileTier = getProfileTier(profileUser?.plan, Boolean(session?.is_guest));
  const profileTierLabel = getProfileTierLabel(profileTier);
  const usageRatio = searchesLimit > 0 ? Math.min(1, searchesToday / searchesLimit) : 0;
  const usagePercent = Math.round(usageRatio * 100);

  const activatePro = async () => {
    if (proPurchaseDisabled) {
      setProBlockedOpen(true);
      return;
    }
    if (!acceptOffer || !offerVersionId) {
      alert(t("proOfferConsentRequired"));
      return;
    }
    try {
      const payment = await createProPayment(token!, offerVersionId);
      if (payment.dev_mode) {
        await devActivatePro(token!);
        const updated = await fetchMe(token!);
        setUser(updated);
        queryClient.invalidateQueries({ queryKey: ["me"] });
        queryClient.invalidateQueries({ queryKey: ["session"] });
        return;
      }
      window.location.href = payment.confirmation_url;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Ошибка оплаты";
      if (message.includes("временно недоступна") || message.includes("недоступна")) {
        setProBlockedOpen(true);
        return;
      }
      alert(message);
    }
  };

  const onDelete = async () => {
    if (!confirm(t("deleteAccountConfirm"))) return;
    await deleteAccount(token);
    await signOut();
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

      {!isPro && (
        <section className="profile-card profile-pro-card">
          <div className="profile-card-head">
            <div className="profile-pro-headline">
              <h2 className="profile-card-title">{t("upgradePro")}</h2>
              <span className="profile-pro-benefits">{t("proBenefits")}</span>
            </div>
            <span className="profile-pro-badge">Pro</span>
          </div>
          <p className="profile-pro-price">{t("proPrice", { price: proPriceRub })}</p>
          <label className="auth-consent-row profile-pro-offer">
            <input
              type="checkbox"
              checked={acceptOffer}
              onChange={(e) => setAcceptOffer(e.target.checked)}
            />
            <span>
              {t("proOfferConsentPrefix")}{" "}
              <button type="button" className="auth-consent-link" onClick={() => setOfferModalOpen(true)}>
                {t("proOfferConsentLink")}
              </button>
            </span>
          </label>
          {(offerLoadError || (offerFetched && !offerLoading && !offerVersionId)) && (
            <p className="profile-hint profile-pro-offer-error">{t("legalDocumentUnavailable")}</p>
          )}
          <button
            type="button"
            className="btn-primary btn-block"
            disabled={!acceptOffer || offerLoading || !offerVersionId}
            onClick={activatePro}
          >
            {t("upgradePro")}
          </button>
          <p className="profile-pro-check-hint">
            {t("checkProPaymentHintPrefix")}{" "}
            <button type="button" className="profile-pro-check-link" onClick={() => void runPaymentConfirm()}>
              {t("checkProPaymentLink")}
            </button>
            {t("checkProPaymentHintSuffix")}
          </p>
        </section>
      )}

      {profileUser && <ProfileAccountSection user={profileUser} token={token} onUserUpdated={onUserUpdated} />}

      {!session?.is_guest && (
        <section className="profile-card profile-support-card">
          <h2 className="profile-card-title">{t("profileSupportTitle")}</h2>
          <p className="profile-hint">{t("profileSupportHint")}</p>
          <button
            type="button"
            className="btn-secondary btn-block"
            onClick={() => {
              setSupportSource("general");
              setSupportModalOpen(true);
            }}
          >
            {t("profileSupportWrite")}
          </button>
          {ticketsWithReplies.length > 0 && (
            <div className="profile-support-replies">
              <h3 className="profile-support-replies-title">{t("profileSupportReplies")}</h3>
              {ticketsWithReplies.slice(0, 3).map((ticket) => {
                const lastReply = ticket.replies[ticket.replies.length - 1];
                return (
                  <div key={ticket.id} className="profile-support-reply-item">
                    <p className="profile-support-reply-text">{lastReply.message}</p>
                    <p className="profile-support-reply-meta">
                      {new Date(lastReply.created_at).toLocaleString("ru-RU")}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      <div className="profile-actions">
        {profileUser?.email && (
          <button
            type="button"
            className="btn-secondary btn-block"
            onClick={() => void signOut()}
          >
            {t("signOut")}
          </button>
        )}
        {!profileUser?.email && inMax && <p className="profile-hint profile-hint--center">{t("maxSignOutHint")}</p>}
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

      <ProPurchaseBlockedModal open={proBlockedOpen} onClose={() => setProBlockedOpen(false)} />
      <ProPaymentStatusModal
        state={paymentModal}
        onClose={() => setPaymentModal({ open: false })}
        onRetry={() => void runPaymentConfirm()}
        onOpenSupport={() => {
          setPaymentModal({ open: false });
          setSupportSource("pro_payment");
          setSupportModalOpen(true);
        }}
      />

      <SupportFormModal
        open={supportModalOpen}
        onClose={() => setSupportModalOpen(false)}
        onSubmit={async (message) => {
          await createSupportTicket(token!, message, supportSource);
          setSupportToast(true);
          void refetchSupportTickets();
        }}
      />

      {supportToast && <SupportToast message={t("supportFormSent")} onDone={() => setSupportToast(false)} />}

      {offerModalOpen && (
        <LegalDocumentModal
          title={offerDoc?.title ?? t("proOfferConsentLink")}
          contentHtml={
            offerLoadError ? `<p>${t("legalDocumentUnavailable")}</p>` : (offerDoc?.content_html ?? "")
          }
          loading={offerLoading}
          onClose={() => setOfferModalOpen(false)}
        />
      )}
    </div>
  );
}
