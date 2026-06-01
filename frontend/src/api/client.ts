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

function apiHeaders(token: string | null, json = true): HeadersInit {
  const h: HeadersInit = { ...getGuestSessionHeader() };
  if (json) (h as Record<string, string>)["Content-Type"] = "application/json";
  if (token) (h as Record<string, string>)["Authorization"] = `Bearer ${token}`;
  return h;
}

async function parseAuthError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return (body as { detail?: string }).detail || "Ошибка авторизации";
  } catch {
    return "Ошибка авторизации";
  }
}

export async function loginWithInitData(initData: string): Promise<{ access_token: string; user: UserProfile }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ init_data: initData }),
  });
  if (!res.ok) throw new Error(await parseAuthError(res));
  return res.json();
}

export async function loginEmail(
  email: string,
  password: string
): Promise<{ access_token: string; user: UserProfile }> {
  const res = await fetch(`${API_BASE}/api/auth/email-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(await parseAuthError(res));
  return res.json();
}

export async function registerEmail(
  email: string,
  password: string,
  firstName?: string
): Promise<{ access_token: string; user: UserProfile }> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password, first_name: firstName }),
  });
  if (!res.ok) throw new Error(await parseAuthError(res));
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
  if (!res.ok) throw new Error(await parseAuthError(res));
  return res.json();
}

export async function bindMax(token: string, initData: string): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/api/auth/bind-max`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
    body: JSON.stringify({ init_data: initData }),
  });
  if (!res.ok) throw new Error(await parseAuthError(res));
  return res.json();
}

export async function startBindMax(token: string): Promise<{ bind_token: string; expires_in: number }> {
  const res = await fetch(`${API_BASE}/api/auth/bind-max/start`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error(await parseAuthError(res));
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
  if (!res.ok) throw new Error(await parseAuthError(res));
  return res.json();
}

export async function fetchSession(token: string | null): Promise<SessionStatus> {
  const res = await fetch(`${API_BASE}/api/auth/session`, {
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to load session");
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
  if (!res.ok) throw new Error("Failed to load profile");
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

export async function devActivatePro(token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/payments/dev-activate`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Не удалось активировать Pro");
}

export async function createProPayment(
  token: string
): Promise<{ confirmation_url: string; dev_mode?: boolean }> {
  const res = await fetch(`${API_BASE}/api/payments/create`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) {
    let msg = "Не удалось создать платёж";
    try {
      const body = await res.json();
      const detail = (body as { detail?: unknown }).detail;
      if (typeof detail === "string") {
        msg = detail;
      } else if (Array.isArray(detail)) {
        msg = detail
          .map((item) => (typeof item === "object" && item && "msg" in item ? String((item as { msg?: string }).msg) : String(item)))
          .join("; ");
      }
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

export async function deleteAccount(token: string): Promise<void> {
  await fetch(`${API_BASE}/api/users/me`, {
    method: "DELETE",
    headers: apiHeaders(token),
    credentials: "include",
  });
}

export interface RouteInfo {
  needs_search: boolean;
  answer_model: string;
  reason?: string;
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
  onToken?: (text: string) => void;
  onResetAnswer?: () => void;
  onFollowUps?: (questions: string[]) => void;
  onDone?: (payload: SearchDonePayload) => void;
  onError?: (message: string, code?: string) => void;
}

export async function submitMessageFeedback(
  token: string,
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

export async function uploadFile(token: string, file: File): Promise<UploadedFile> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/files/upload`, {
    method: "POST",
    headers: token
      ? { Authorization: `Bearer ${token}`, ...getGuestSessionHeader() }
      : getGuestSessionHeader(),
    credentials: "include",
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = (err as { detail?: UploadErrorDetail }).detail;
    throw parseUploadErrorDetail(detail);
  }
  return res.json();
}

export async function transcribeVoice(
  token: string,
  blob: Blob,
): Promise<{ text: string }> {
  const ext =
    blob.type.includes("mp4") ? "m4a" : blob.type.includes("ogg") ? "ogg" : "webm";
  const file = new File([blob], `voice.${ext}`, {
    type: blob.type || "audio/webm",
  });
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/api/voice/transcribe`, {
    method: "POST",
    headers: token
      ? { Authorization: `Bearer ${token}`, ...getGuestSessionHeader() }
      : getGuestSessionHeader(),
    credentials: "include",
    body: form,
  });
  if (!res.ok) {
    let msg = "Не удалось распознать речь";
    try {
      const err = await res.json();
      const detail = (err as { detail?: string }).detail;
      if (detail) msg = detail;
    } catch {
      /* ignore */
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

export async function streamSearch(
  token: string | null,
  query: string,
  threadId: string | null,
  attachmentIds: string[],
  handlers: SSEHandlers,
  signal?: AbortSignal
): Promise<void> {
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
      msg = (err as { detail?: string }).detail || msg;
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
          case "token":
            handlers.onToken?.(parsed.text);
            break;
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
            handlers.onError?.(parsed.message, parsed.code as string | undefined);
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
