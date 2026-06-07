import { confirmProPayment, fetchMe } from "../api/client";

export const PRO_PAYMENT_PENDING_KEY = "glosix-pro-payment-pending";
export const MAX_PAY_RETURN_START_PARAM = "pay_ok";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

export function markProPaymentPending(): void {
  try {
    sessionStorage.setItem(PRO_PAYMENT_PENDING_KEY, String(Date.now()));
  } catch {
    /* ignore */
  }
}

export function clearProPaymentPending(): void {
  try {
    sessionStorage.removeItem(PRO_PAYMENT_PENDING_KEY);
  } catch {
    /* ignore */
  }
}

export function hasProPaymentPending(): boolean {
  try {
    return Boolean(sessionStorage.getItem(PRO_PAYMENT_PENDING_KEY));
  } catch {
    return false;
  }
}

export type ProPaymentConfirmResult =
  | { kind: "success" }
  | { kind: "already_pro" }
  | { kind: "pending"; message?: string }
  | { kind: "error"; message: string; canRetry: boolean; showSupportLink?: boolean };

export async function runProPaymentConfirm(
  token: string,
  options?: { retries?: number },
): Promise<ProPaymentConfirmResult> {
  const retries = options?.retries ?? 4;
  for (let attempt = 0; attempt < retries; attempt += 1) {
    const result = await confirmProPayment(token);
    if (result.ok && result.plan === "pro") {
      clearProPaymentPending();
      return result.already_active ? { kind: "already_pro" } : { kind: "success" };
    }
    if (result.ok && result.plan !== "pro") {
      return {
        kind: "error",
        message: "Оплата найдена, но тариф не обновился. Обновите страницу или напишите в поддержку.",
        canRetry: true,
      };
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

    return {
      kind: isPending ? "pending" : "error",
      message:
        result.message ||
        (isPending ? "Платёж обрабатывается. Подождите несколько секунд." : "Успешная оплата не найдена."),
      canRetry: !paymentNotFound,
      showSupportLink: paymentNotFound,
    };
  }

  return {
    kind: "error",
    message: "Не удалось подтвердить оплату",
    canRetry: true,
  };
}

export async function refreshUserAfterProPayment(
  token: string,
  setUser: (user: Awaited<ReturnType<typeof fetchMe>>) => void,
  invalidate?: () => void,
): Promise<void> {
  const updated = await fetchMe(token);
  setUser(updated);
  invalidate?.();
}
