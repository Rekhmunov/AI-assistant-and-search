import { formatApiErrorDetail } from "../lib/apiErrorDetail";
import { HttpResponseError, isAuthFailureStatus, isTransientFailureStatus } from "../lib/httpError";
import { clearGuestSession, getGuestSessionHeader, saveGuestSession } from "../lib/guestSession";

const API_BASE = import.meta.env.VITE_API_URL || "";

export type Plan = "free" | "pro";

export interface SessionStatus {
  authenticated: boolean;
  is_guest: boolean;
  searches_today: number;
  searches_limit: number;
  pro_price_rub?: number;
  user?: UserProfile | null;
}

export interface UserProfile {
  id: string;
  email?: string | null;
  max_linked?: boolean;
  /** Стабильный ID аккаунта в MAX (только для отображения владельцу). */
  max_user_id?: number | null;
  first_name: string | null;
  last_name: string | null;
  username: string | null;
  language: string;
  plan: Plan;
  plan_expires_at: string | null;
  searches_today: number;
  searches_limit: number;
  pro_price_rub?: number;
}

export interface AppPublicConfig {
  pro_price_rub: number;
  pro_purchase_disabled?: boolean;
  yandex_metrica_counter_id?: string | null;
  yandex_webmaster_verification?: string | null;
}

export interface ThreadListItem {
  id: string;
  title: string;
  message_count: number;
  is_saved: boolean;
  last_message_at: string;
}

export interface Source {
  index: number;
  url: string;
  title: string;
  snippet: string;
  domain: string;
}

export interface MessageAttachment {
  id: string;
  filename: string;
  kind: "document" | "image" | "markdown_document";
  url?: string | null;
  share_url?: string | null;
  ttl_hours?: number | null;
  previewUrl?: string;
  title?: string | null;
  content?: string | null;
}

export interface MarkdownDocumentInfo {
  title: string;
  content: string;
  collapsible?: boolean;
}

export interface GeneratedDocumentInfo {
  id: string;
  filename: string;
  url?: string | null;
  share_url?: string | null;
  ttl_hours?: number;
}

export interface EntityImage {
  url: string;
  title: string;
  page_url: string;
  width?: number | null;
  height?: number | null;
}

export interface MessageFeedback {
  rating: "up" | "down";
  reason_code?: string | null;
  reason_label?: string | null;
  comment?: string | null;
}

export type FeedbackReasonCode = "outdated" | "inaccurate" | "wrong_sources" | "other";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[] | null;
  attachments?: MessageAttachment[] | null;
  images?: EntityImage[] | null;
  follow_up_questions: string[] | null;
  user_feedback?: MessageFeedback | null;
  created_at: string;
}

export interface ThreadDetail {
  id: string;
  title: string;
  is_saved: boolean;
  messages: Message[];
}

export interface AnswerStatus {
  pending: boolean;
  active: boolean;
  stale: boolean;
  active_age_sec: number | null;
  phase: string | null;
  needs_search: boolean | null;
  custom_status: string | null;
  user_message_id: string | null;
  query: string | null;
}

function apiHeaders(token: string | null, json = true): HeadersInit {
  const h: HeadersInit = { ...getGuestSessionHeader() };
  if (json) (h as Record<string, string>)["Content-Type"] = "application/json";
  if (token) (h as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  return h;
}

function serverUnavailableMessage(status: number): string | null {
  if (status === 500 || status === 502 || status === 503 || status === 504) {
    return "Сервер временно недоступен. Попробуйте через минуту.";
  }
  return null;
}

async function parseAuthError(res: Response): Promise<string> {
  const fallback =
    serverUnavailableMessage(res.status) ??
    (res.status === 403
      ? "Запрос отклонён. Откройте сайт с официального адреса glosix.ru."
      : res.status === 429
        ? "Слишком много попыток. Попробуйте позже."
        : "Ошибка авторизации");
  try {
    const body = await res.json();
    const text = formatApiErrorDetail(body, fallback);
    if (serverUnavailableMessage(res.status) && text === "Ошибка авторизации") {
      return serverUnavailableMessage(res.status)!;
    }
    return text;
  } catch {
    return `${fallback} (код ${res.status})`;
  }
}

async function throwHttpError(res: Response, parse: (r: Response) => Promise<string>): Promise<never> {
  const message = await parse(res);
  throw new HttpResponseError(message, res.status);
}

export async function loginWithInitData(initData: string): Promise<{ access_token: string; user: UserProfile }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ init_data: initData }),
  });
  if (!res.ok) await throwHttpError(res, parseAuthError);
  return res.json();
}

export async function loginEmail(
  email: string,
  password: string
): Promise<{ access_token: string; user: UserProfile }> {
  const res = await fetch(`${API_BASE}/api/auth/email-login`, {
    method: "POST",
    headers: apiHeaders(null),
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) await throwHttpError(res, parseAuthError);
  return res.json();
}

export type LegalRoute = {
  slug: string;
  title: string;
  public_path: string;
  version_id: string;
};

export type LegalDocumentPublic = {
  slug: string;
  title: string;
  public_path: string;
  version_id: string;
  version_number: number;
  content_html: string;
};

export async function fetchLegalRoutes(): Promise<LegalRoute[]> {
  const res = await fetch(`${API_BASE}/api/legal/routes`, { credentials: "include" });
  if (!res.ok) return [];
  return res.json();
}

export async function fetchLegalRegisterMeta(): Promise<{ documents: LegalRoute[] }> {
  const res = await fetch(`${API_BASE}/api/legal/register-meta`, { credentials: "include" });
  if (!res.ok) return { documents: [] };
  return res.json();
}

export async function fetchLegalBySlug(slug: string): Promise<LegalDocumentPublic> {
  const res = await fetch(`${API_BASE}/api/legal/${encodeURIComponent(slug)}`, {
    credentials: "include",
  });
  if (!res.ok) throw new Error("Document not found");
  return res.json();
}

export async function fetchLegalByPath(path: string): Promise<LegalDocumentPublic> {
  const params = new URLSearchParams({ path });
  const res = await fetch(`${API_BASE}/api/legal/by-path?${params}`, { credentials: "include" });
  if (!res.ok) throw new Error("Document not found");
  return res.json();
}

export type PendingConsent = {
  slug: string;
  title: string;
  public_path: string;
  version_id: string;
  version_number: number;
};

export async function fetchConsentStatus(
  token: string,
): Promise<{ pending: PendingConsent[] }> {
  const res = await fetch(`${API_BASE}/api/legal/consent-status`, {
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to load consent status");
  return res.json();
}

export async function recordLegalConsent(
  token: string | null,
  body: {
    consents: Array<{ slug: string; version_id: string }>;
    source: string;
    consent_method: string;
  },
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/legal/consent`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = "Failed to record consent";
    try {
      const data = await res.json();
      if (typeof data.detail === "string") msg = data.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
}

export async function registerEmail(
  email: string,
  password: string,
  firstName: string | undefined,
  consents: { privacy_version_id: string; pd_consent_version_id: string },
): Promise<{ access_token: string; user: UserProfile }> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: apiHeaders(null),
    credentials: "include",
    body: JSON.stringify({
      email,
      password,
      first_name: firstName || null,
      privacy_version_id: consents.privacy_version_id,
      pd_consent_version_id: consents.pd_consent_version_id,
    }),
  });
  if (!res.ok) await throwHttpError(res, parseAuthError);
  return res.json();
}

export async function changePassword(
  token: string,
  currentPassword: string,
  newPassword: string,
): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/api/auth/change-password`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
  if (!res.ok) await throwHttpError(res, parseAuthError);
  return res.json();
}

export async function bindEmail(
  token: string,
  email: string,
  password: string,
  firstName?: string
): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/api/auth/bind-email`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
    body: JSON.stringify({ email, password, first_name: firstName }),
  });
  if (!res.ok) await throwHttpError(res, parseAuthError);
  return res.json();
}

export async function bindMax(token: string, initData: string): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/api/auth/bind-max`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
    body: JSON.stringify({ init_data: initData }),
  });
  if (!res.ok) await throwHttpError(res, parseAuthError);
  return res.json();
}

export async function startBindMax(token: string): Promise<{ bind_token: string; expires_in: number }> {
  const res = await fetch(`${API_BASE}/api/auth/bind-max/start`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) await throwHttpError(res, parseAuthError);
  return res.json();
}

export async function completeBindMax(
  bindToken: string,
  initData: string,
): Promise<{ access_token: string; user: UserProfile }> {
  const res = await fetch(`${API_BASE}/api/auth/bind-max/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ bind_token: bindToken, init_data: initData }),
  });
  if (!res.ok) await throwHttpError(res, parseAuthError);
  return res.json();
}

export async function fetchSession(token: string | null): Promise<SessionStatus> {
  const res = await fetch(`${API_BASE}/api/auth/session`, {
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) {
    const msg = serverUnavailableMessage(res.status) ?? "Failed to load session";
    throw new HttpResponseError(msg, res.status);
  }
  const guestKey = res.headers.get("X-Guest-Session");
  if (guestKey) saveGuestSession(guestKey);
  return res.json();
}

export async function logoutSession(): Promise<void> {
  const res = await fetch(`${API_BASE}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok && !isTransientFailureStatus(res.status)) {
    await throwHttpError(res, parseAuthError);
  }
}

export async function refreshAccessToken(): Promise<{ access_token: string }> {
  const res = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) await throwHttpError(res, parseAuthError);
  return res.json();
}

export async function fetchAppConfig(): Promise<AppPublicConfig> {
  const res = await fetch(`${API_BASE}/api/config/public?_=${Date.now()}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to load app config");
  return res.json();
}

export async function fetchMe(token: string): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/api/users/me`, {
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) {
    const msg = serverUnavailableMessage(res.status) ?? "Failed to load profile";
    throw new HttpResponseError(msg, res.status);
  }
  return res.json();
}

export async function fetchThreads(token: string): Promise<ThreadListItem[]> {
  const res = await fetch(`${API_BASE}/api/threads`, {
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to load threads");
  return res.json();
}

export async function searchThreads(token: string, query: string): Promise<ThreadListItem[]> {
  const params = new URLSearchParams({ q: query.trim() });
  const res = await fetch(`${API_BASE}/api/threads/search?${params}`, {
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to search threads");
  return res.json();
}

export async function fetchThread(token: string | null, id: string): Promise<ThreadDetail> {
  const res = await fetch(`${API_BASE}/api/threads/${id}`, {
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to load thread");
  return res.json();
}

export async function fetchAnswerStatus(
  token: string | null,
  threadId: string,
): Promise<AnswerStatus> {
  const res = await fetch(`${API_BASE}/api/threads/${threadId}/answer-status`, {
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to load answer status");
  return res.json();
}

export async function saveThread(token: string, id: string): Promise<void> {
  await fetch(`${API_BASE}/api/threads/${id}/save`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
  });
}

export async function renameThread(token: string, id: string, title: string): Promise<ThreadListItem> {
  const res = await fetch(`${API_BASE}/api/threads/${id}`, {
    method: "PATCH",
    headers: apiHeaders(token),
    credentials: "include",
    body: JSON.stringify({ title }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to rename thread");
  }
  return res.json();
}

export async function deleteThread(token: string, id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/threads/${id}`, {
    method: "DELETE",
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok && res.status !== 204) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to delete thread");
  }
}

export async function deleteThreadsBulk(
  token: string,
  threadIds: string[],
): Promise<{ deleted: number; not_found: number }> {
  const res = await fetch(`${API_BASE}/api/threads/bulk-delete`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
    body: JSON.stringify({ thread_ids: threadIds }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to delete threads");
  }
  return res.json();
}

export async function devActivatePro(token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/payments/dev-activate`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Не удалось активировать Pro");
}

export async function createProPayment(
  token: string,
  offerVersionId: string,
  options?: { fromMax?: boolean },
): Promise<{ confirmation_url: string; dev_mode?: boolean }> {
  const res = await fetch(`${API_BASE}/api/payments/create`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
    body: JSON.stringify({
      offer_version_id: offerVersionId,
      from_max: Boolean(options?.fromMax),
    }),
  });
  if (!res.ok) {
    let msg = "Не удалось создать платёж";
    try {
      const body = await res.json();
      msg = formatApiErrorDetail(body, msg);
      if (msg === "Internal server error") {
        msg = "Не удалось создать платёж. Попробуйте позже или напишите в поддержку.";
      }
    } catch {
      if (res.status >= 500) {
        msg = "Не удалось создать платёж. Попробуйте позже или напишите в поддержку.";
      }
    }
    throw new Error(msg);
  }
  return res.json();
}

export type SupportTicketUser = {
  id: string;
  source: string;
  message: string;
  status: string;
  created_at: string;
  closed_at: string | null;
  has_unread_reply: boolean;
  can_reply: boolean;
  replies: Array<{
    id: string;
    author_type: string;
    admin_email: string | null;
    message: string;
    created_at: string;
  }>;
};

export async function fetchMySupportTickets(token: string): Promise<SupportTicketUser[]> {
  const res = await fetch(`${API_BASE}/api/support/tickets`, {
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) return [];
  const data = (await res.json()) as SupportTicketUser[];
  return data.map((ticket) => ({
    ...ticket,
    has_unread_reply: ticket.has_unread_reply ?? false,
    can_reply: ticket.can_reply ?? ticket.status !== "closed",
  }));
}

export async function replyToSupportTicket(
  token: string,
  ticketId: string,
  message: string,
): Promise<SupportTicketUser> {
  const res = await fetch(`${API_BASE}/api/support/tickets/${ticketId}/replies`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
    body: JSON.stringify({ message }),
  });
  if (!res.ok) {
    let msg = "Не удалось отправить сообщение";
    try {
      const body = await res.json();
      msg = formatApiErrorDetail(body, msg);
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

export async function markSupportTicketRead(
  token: string,
  ticketId: string,
): Promise<SupportTicketUser> {
  const res = await fetch(`${API_BASE}/api/support/tickets/${ticketId}/read`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to mark ticket read");
  return res.json();
}

export async function createSupportTicket(
  token: string,
  message: string,
  source = "general",
): Promise<{ id: string; created_at: string }> {
  const res = await fetch(`${API_BASE}/api/support/tickets`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
    body: JSON.stringify({ message, source }),
  });
  if (!res.ok) {
    let msg = "Не удалось отправить сообщение";
    try {
      const body = await res.json();
      msg = formatApiErrorDetail(body, msg);
      if (msg === "Internal server error") {
        msg = "Сервис поддержки временно недоступен. Попробуйте позже.";
      }
    } catch {
      if (res.status >= 500) msg = "Сервис поддержки временно недоступен. Попробуйте позже.";
    }
    throw new Error(msg);
  }
  return res.json();
}

export async function confirmProPayment(
  token: string
): Promise<{
  ok: boolean;
  plan?: string;
  message?: string;
  already_active?: boolean;
  status?: string;
  source?: string;
  payment_id?: string;
}> {
  const res = await fetch(`${API_BASE}/api/payments/confirm`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) {
    let msg = "Не удалось подтвердить оплату";
    try {
      const body = await res.json();
      const detail = (body as { detail?: unknown }).detail;
      if (typeof detail === "string") msg = detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

export async function deleteAccount(token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/users/me`, {
    method: "DELETE",
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) await throwHttpError(res, parseAuthError);
}

export interface RouteInfo {
  needs_search: boolean;
  answer_model: string;
  reason?: string;
  intent?: string;
}

export interface SearchDonePayload {
  message_id?: string;
  searches_today?: number;
  searches_limit?: number;
}

export interface SSEHandlers {
  onThread?: (id: string) => void;
  onRoute?: (route: RouteInfo) => void;
  onSources?: (sources: Source[]) => void;
  onImages?: (images: EntityImage[]) => void;
  onImageGenStart?: (status: string) => void;
  onImageGenStatus?: (status: string) => void;
  onDocGenStart?: (status: string) => void;
  onDocGenStatus?: (status: string) => void;
  onDocumentReady?: (doc: GeneratedDocumentInfo) => void;
  onMarkdownDocument?: (doc: MarkdownDocumentInfo) => void;
  onToken?: (text: string) => void;
  onResetAnswer?: () => void;
  onFollowUps?: (questions: string[]) => void;
  onDone?: (payload: SearchDonePayload) => void;
  onError?: (message: string, code?: string) => void;
}

export async function submitMessageFeedback(
  token: string | null,
  messageId: string,
  body: {
    rating: "up" | "down";
    reason_code?: FeedbackReasonCode | null;
    comment?: string | null;
  },
): Promise<{ ok: boolean; feedback: MessageFeedback }> {
  const res = await fetch(`${API_BASE}/api/messages/${messageId}/feedback`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = "Не удалось отправить оценку";
    try {
      const err = await res.json();
      msg = (err as { detail?: string }).detail || msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  const guestKey = res.headers.get("X-Guest-Session");
  if (guestKey) saveGuestSession(guestKey);
  return res.json();
}

export interface UploadedFile {
  id: string;
  filename: string;
  size_bytes: number;
  excerpt: string;
}

export class FileUploadError extends Error {
  suggestPro: boolean;

  constructor(message: string, suggestPro = false) {
    super(message);
    this.name = "FileUploadError";
    this.suggestPro = suggestPro;
  }
}

type UploadErrorDetail =
  | string
  | {
      code?: string;
      message?: string;
      suggest_pro?: boolean;
    };

function parseUploadErrorDetail(detail: UploadErrorDetail | undefined): FileUploadError {
  if (!detail) {
    return new FileUploadError("Не удалось загрузить файл");
  }
  if (typeof detail === "string") {
    return new FileUploadError(detail);
  }
  const message = detail.message || "Не удалось загрузить файл";
  return new FileUploadError(message, Boolean(detail.suggest_pro));
}

async function uploadFilename(file: File, kind?: "document" | "image"): Promise<string> {
  const name = file.name?.trim();
  if (name && name !== "blob" && name.includes(".")) return name;
  if (file.type?.startsWith("image/") || kind === "image") {
    const ext = file.type?.split("/")[1]?.replace("jpeg", "jpg");
    if (ext && ext !== "octet-stream") return `photo.${ext}`;
    const { sniffImageExt } = await import("../constants/files");
    const buf = await file.slice(0, 16).arrayBuffer();
    const sniffed = sniffImageExt(new Uint8Array(buf));
    return `photo.${sniffed ?? "jpg"}`;
  }
  if (name && name !== "blob") return name;
  return "document.bin";
}

export async function uploadFile(
  token: string | null,
  file: File,
  kind?: "document" | "image",
): Promise<UploadedFile> {
  const form = new FormData();
  form.append("file", file, await uploadFilename(file, kind));
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/files/upload`, {
      method: "POST",
      headers: token
        ? { Authorization: `Bearer ${token}`, ...getGuestSessionHeader() }
        : getGuestSessionHeader(),
      credentials: "include",
      body: form,
    });
  } catch {
    throw new FileUploadError("Не удалось загрузить файл. Проверьте соединение и попробуйте снова.");
  }
  if (!res.ok) {
    if (res.status === 413) {
      throw new FileUploadError(
        "Файл слишком большой для загрузки. Попробуйте уменьшить фото или перейдите на Pro.",
      );
    }
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: UploadErrorDetail }).detail;
    throw parseUploadErrorDetail(detail);
  }
  const guestKey = res.headers.get("X-Guest-Session");
  if (guestKey) saveGuestSession(guestKey);
  return res.json();
}

export async function fetchFileMeta(
  token: string,
  fileId: string,
): Promise<{ id: string; filename: string; media_kind: string; preview_url: string | null }> {
  const res = await fetch(`${API_BASE}/api/files/${fileId}/meta`, {
    headers: apiHeaders(token, false),
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error("Не удалось загрузить данные файла");
  }
  return res.json();
}

function normalizeApiPath(path: string): string {
  return path.startsWith("http") ? path : path.startsWith("/") ? path : `/${path}`;
}

function resolveAbsoluteApiUrl(path: string): string {
  const normalized = normalizeApiPath(path);
  if (normalized.startsWith("http")) return normalized;
  if (typeof window !== "undefined" && window.location?.origin) {
    return `${window.location.origin}${normalized}`;
  }
  const base = (API_BASE || "").replace(/\/$/, "");
  return base ? `${base}${normalized}` : normalized;
}

/** Word из текста блока ответа (```txt), без нового запроса в чат. */
export async function exportAnswerBlockToDocx(
  token: string | null,
  content: string,
  title?: string,
): Promise<GeneratedDocumentInfo> {
  const res = await fetch(`${API_BASE}/api/files/export-docx`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
    body: JSON.stringify({ content, title: title ?? null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: string }).detail;
    throw new Error(typeof detail === "string" ? detail : "Не удалось сформировать документ");
  }
  const data = (await res.json()) as {
    id: string;
    filename: string;
    url?: string | null;
    share_url: string;
    ttl_hours: number;
  };
  return {
    id: String(data.id),
    filename: data.filename,
    url: data.url ?? undefined,
    share_url: data.share_url,
    ttl_hours: data.ttl_hours,
  };
}

/** Прямая ссылка на .docx (share предпочтительнее — работает в новой вкладке без Bearer). */
export function resolveGeneratedDocumentOpenUrl(
  doc: Pick<GeneratedDocumentInfo, "id" | "share_url" | "url">,
): string {
  if (doc.share_url?.trim()) return resolveAbsoluteApiUrl(doc.share_url.trim());
  if (doc.url?.trim()) return resolveAbsoluteApiUrl(doc.url.trim());
  return resolveAbsoluteApiUrl(`/api/files/${doc.id}/content`);
}

function appendFileFetchUrl(urls: string[], path: string) {
  const normalized = normalizeApiPath(path);
  if (normalized.startsWith("http")) {
    urls.push(normalized);
    return;
  }
  if (typeof window !== "undefined" && window.location?.origin) {
    urls.push(`${window.location.origin}${normalized}`);
  }
  const base = (API_BASE || "").replace(/\/$/, "");
  if (base) urls.push(`${base}${normalized}`);
}

function buildFileFetchUrls(
  fileId: string,
  opts?: { shareUrl?: string | null; downloadUrl?: string | null },
): string[] {
  const urls: string[] = [];
  if (opts?.shareUrl?.trim()) appendFileFetchUrl(urls, opts.shareUrl.trim());
  if (opts?.downloadUrl?.trim()) appendFileFetchUrl(urls, opts.downloadUrl.trim());
  appendFileFetchUrl(urls, `/api/files/${fileId}/content`);
  return [...new Set(urls)];
}

async function blobLooksLikeApiError(blob: Blob): Promise<boolean> {
  if (blob.size >= 256) return false;
  if (!blob.type.includes("json") && !blob.type.includes("text") && !blob.type.includes("html")) {
    return false;
  }
  const headText = await blob.slice(0, Math.min(blob.size, 200)).text();
  const trimmed = headText.trim();
  return trimmed.startsWith("{") || trimmed.startsWith("<") || headText.includes('"detail"');
}

async function fetchFileOnce(url: string, token: string | null): Promise<Blob | null> {
  const shared = url.includes("/shared?");
  const res = await fetch(url, {
    headers: shared ? undefined : apiHeaders(token, false),
    credentials: "include",
  });
  if (!res.ok) return null;
  const blob = await res.blob();
  if (await blobLooksLikeApiError(blob)) return null;
  return blob;
}

/** Бинарник файла: share (без JWT), затем /content с cookie/Bearer. */
export async function fetchFileContent(
  token: string | null,
  fileId: string,
  opts?: { shareUrl?: string | null; downloadUrl?: string | null },
): Promise<Blob> {
  let accessToken = token;
  const urls = buildFileFetchUrls(fileId, opts);

  for (let attempt = 0; attempt < 2; attempt++) {
    for (const url of urls) {
      const blob = await fetchFileOnce(url, accessToken);
      if (blob) return blob;
    }
    if (attempt > 0) break;
    try {
      const refreshed = await refreshAccessToken();
      accessToken = refreshed.access_token;
      useAuthStore.getState().setToken(accessToken);
    } catch {
      break;
    }
  }
  throw new Error("Не удалось загрузить файл");
}

export type VoiceClientReportPayload = {
  event: string;
  bytes?: number;
  platform?: string;
  max_webapp?: boolean;
  mime?: string;
  elapsed_ms?: number;
  error?: string;
};

/** Лог на сервере, если /transcribe не вызывается (пустой blob, сеть). */
export async function reportVoiceClient(payload: VoiceClientReportPayload): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/voice/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...getGuestSessionHeader() },
      credentials: "include",
      body: JSON.stringify({
        api_base: API_BASE || "(same-origin)",
        ...payload,
      }),
    });
  } catch {
    /* ignore */
  }
}

export async function transcribeVoice(
  token: string | null,
  blob: Blob,
  mimeHint?: string,
): Promise<{ text: string }> {
  const mime = (mimeHint || blob.type || "audio/webm").split(";")[0].trim().toLowerCase();
  const ext = mime.includes("mp4") || mime.includes("aac")
    ? "m4a"
    : mime.includes("ogg")
      ? "ogg"
      : mime.includes("mpeg") || mime.includes("mp3")
        ? "mp3"
        : mime.includes("wav")
          ? "wav"
          : "webm";
  const buildForm = () => {
    const file = new File([blob], `voice.${ext}`, {
      type: mime || "audio/webm",
    });
    const form = new FormData();
    form.append("file", file);
    return form;
  };

  const postTranscribe = async (accessToken: string | null) =>
    fetch(`${API_BASE}/api/voice/transcribe`, {
      method: "POST",
      headers: accessToken
        ? { Authorization: `Bearer ${accessToken}`, ...getGuestSessionHeader() }
        : getGuestSessionHeader(),
      credentials: "include",
      body: buildForm(),
    });

  let res = await postTranscribe(token);
  if (res.status === 401) {
    try {
      const refreshed = await refreshAccessToken();
      res = await postTranscribe(refreshed.access_token);
    } catch {
      /* keep original 401 response */
    }
  }
  if (!res.ok) {
    let msg = "Не удалось распознать речь";
    try {
      const err = await res.json();
      const detail = (err as { detail?: string }).detail;
      if (detail) msg = detail;
    } catch {
      /* ignore */
    }
    if (res.status === 401) {
      msg = "Сессия недоступна. Закройте миниапп и откройте снова из бота";
    } else if (res.status === 0 || res.type === "opaque") {
      msg = "Нет связи с API. Проверьте интернет";
    }
    throw new Error(msg);
  }
  return res.json();
}

function networkErrorMessage(err: unknown): string {
  if (err instanceof TypeError) {
    return "Нет связи с сервером. Проверьте интернет и обновите страницу.";
  }
  if (err instanceof Error) {
    const m = err.message.toLowerCase();
    if (m.includes("network") || m.includes("failed to fetch") || m.includes("load failed")) {
      return "Нет связи с сервером. Проверьте интернет и обновите страницу.";
    }
    return err.message;
  }
  return "Нет связи с сервером. Попробуйте ещё раз.";
}

export type StreamSearchOptions = {
  retryPending?: boolean;
  signal?: AbortSignal;
};

export async function streamSearch(
  token: string | null,
  query: string,
  threadId: string | null,
  attachmentIds: string[],
  handlers: SSEHandlers,
  options?: StreamSearchOptions,
): Promise<void> {
  const signal = options?.signal;
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/search`, {
      method: "POST",
      headers: apiHeaders(token),
      credentials: "include",
      body: JSON.stringify({
        query,
        thread_id: threadId,
        attachment_ids: attachmentIds.length ? attachmentIds : null,
        retry_pending: Boolean(options?.retryPending),
      }),
      signal,
    });
  } catch (err) {
    handlers.onError?.(networkErrorMessage(err), "network_error");
    return;
  }

  const guestKey = res.headers.get("X-Guest-Session");
  if (guestKey) saveGuestSession(guestKey);

  if (!res.ok || !res.body) {
    let msg = "Ошибка поиска";
    try {
      const err = await res.json();
      msg = formatApiErrorDetail(err, msg);
    } catch {
      /* ignore */
    }
    handlers.onError?.(msg);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;
  let gotError = false;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const lines = part.split("\n");
        let event = "message";
        let data = "";
        for (const line of lines) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:")) data = line.slice(5).trim();
        }
        if (!data) continue;
        const parsed = JSON.parse(data);
        switch (event) {
          case "thread":
            handlers.onThread?.(parsed.thread_id);
            break;
          case "route":
            handlers.onRoute?.(parsed as RouteInfo);
            break;
          case "sources":
            handlers.onSources?.(Array.isArray(parsed.sources) ? parsed.sources : []);
            break;
          case "images":
            handlers.onImages?.(Array.isArray(parsed.images) ? parsed.images : []);
            break;
          case "image_gen_start":
            if (typeof parsed.status === "string") handlers.onImageGenStart?.(parsed.status);
            break;
          case "image_gen_status":
            if (typeof parsed.status === "string") handlers.onImageGenStatus?.(parsed.status);
            break;
          case "doc_gen_start":
            if (typeof parsed.status === "string") handlers.onDocGenStart?.(parsed.status);
            break;
          case "doc_gen_status":
            if (typeof parsed.status === "string") handlers.onDocGenStatus?.(parsed.status);
            break;
          case "document_ready":
            handlers.onDocumentReady?.({
              id: String(parsed.file_id ?? ""),
              filename: String(parsed.filename ?? "document.docx"),
              url: parsed.download_url as string | undefined,
              share_url: parsed.share_url as string | undefined,
              ttl_hours: typeof parsed.ttl_hours === "number" ? parsed.ttl_hours : undefined,
            });
            break;
          case "markdown_document":
            handlers.onMarkdownDocument?.({
              title: String(parsed.title ?? "Документ"),
              content: String(parsed.content ?? ""),
              collapsible: Boolean(parsed.collapsible),
            });
            break;
          case "token": {
            const chunk = parsed.text;
            if (typeof chunk === "string") handlers.onToken?.(chunk);
            else if (chunk != null) handlers.onToken?.(String(chunk));
            break;
          }
          case "reset_answer":
            handlers.onResetAnswer?.();
            break;
          case "follow_ups":
            handlers.onFollowUps?.(parsed.questions);
            break;
          case "done":
            finished = true;
            handlers.onDone?.(parsed as SearchDonePayload);
            break;
          case "error":
            gotError = true;
            handlers.onError?.(
              typeof parsed.message === "string"
                ? parsed.message
                : formatApiErrorDetail({ detail: parsed.message }, "Ошибка поиска"),
              parsed.code as string | undefined,
            );
            break;
        }
      }
    }
  } catch (e) {
    if (!gotError && !finished) {
      gotError = true;
      handlers.onError?.(networkErrorMessage(e), "network_error");
    }
  } finally {
    if (!finished && !gotError) {
      handlers.onError?.("Соединение прервано. Попробуйте ещё раз.", "network_error");
    }
  }
}
