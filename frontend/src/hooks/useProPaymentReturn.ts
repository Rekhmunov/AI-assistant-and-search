import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  hasProPaymentPending,
  MAX_PAY_RETURN_START_PARAM,
  refreshUserAfterProPayment,
  runProPaymentConfirm,
  type ProPaymentConfirmResult,
} from "../lib/proPaymentReturn";
import { getMaxStartParam, isMaxWebApp, parseMaxBindToken } from "../lib/maxApp";
import { useAuthStore } from "../store/authStore";

export type ProPaymentReturnModalState =
  | { open: false }
  | { open: true; kind: "loading" }
  | { open: true; kind: "success" }
  | { open: true; kind: "error"; message: string; canRetry: boolean; showSupportLink?: boolean }
  | { open: true; kind: "pending"; message?: string; canRetry: boolean };

function shouldAutoConfirmPayment(): boolean {
  if (!isMaxWebApp()) return false;
  const startParam = getMaxStartParam().trim();
  if (startParam === MAX_PAY_RETURN_START_PARAM) return true;
  if (parseMaxBindToken(startParam)) return false;
  return hasProPaymentPending();
}

export function useProPaymentReturn(ready: boolean) {
  const token = useAuthStore((s) => s.token);
  const setUser = useAuthStore((s) => s.setUser);
  const userPlan = useAuthStore((s) => s.user?.plan);
  const navigate = useNavigate();
  const confirmInFlight = useRef(false);
  const autoConfirmStartedRef = useRef(false);
  const [modal, setModal] = useState<ProPaymentReturnModalState>({ open: false });

  const applyConfirmResult = async (result: ProPaymentConfirmResult, silent: boolean) => {
    if (result.kind === "success" || result.kind === "already_pro") {
      await refreshUserAfterProPayment(token!, setUser);
      if (!silent) {
        setModal({ open: true, kind: "success" });
      }
      if (isMaxWebApp()) {
        navigate("/profile", { replace: true });
      }
      return;
    }
    if (result.kind === "pending") {
      if (!silent) {
        setModal({
          open: true,
          kind: "pending",
          message: result.message ?? "Платёж обрабатывается.",
          canRetry: true,
        });
      }
      return;
    }
    if (!silent) {
      setModal({
        open: true,
        kind: "error",
        message: result.message,
        canRetry: result.canRetry,
        showSupportLink: result.showSupportLink,
      });
    }
  };

  const runConfirm = async (options?: { silent?: boolean; retries?: number }) => {
    if (!token || confirmInFlight.current) return;
    if (userPlan === "pro") {
      return;
    }
    confirmInFlight.current = true;
    if (!options?.silent) {
      setModal({ open: true, kind: "loading" });
    }
    try {
      const result = await runProPaymentConfirm(token, { retries: options?.retries ?? 4 });
      await applyConfirmResult(result, options?.silent ?? false);
    } catch (err) {
      if (!options?.silent) {
        setModal({
          open: true,
          kind: "error",
          message: err instanceof Error ? err.message : "Не удалось активировать Pro",
          canRetry: true,
        });
      }
    } finally {
      confirmInFlight.current = false;
    }
  };

  useEffect(() => {
    if (!ready || !token || userPlan === "pro") return;
    if (!shouldAutoConfirmPayment()) return;
    if (autoConfirmStartedRef.current) return;
    autoConfirmStartedRef.current = true;
    void runConfirm();
  }, [ready, token, userPlan]);

  useEffect(() => {
    if (!ready || !token || !isMaxWebApp() || userPlan === "pro") return;

    const onVisibility = () => {
      if (document.visibilityState !== "visible") return;
      if (!hasProPaymentPending()) return;
      void runConfirm({ silent: true, retries: 3 });
    };

    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [ready, token, userPlan]);

  return {
    modal,
    setModal,
    retryConfirm: () => void runConfirm({ retries: 4 }),
  };
}
