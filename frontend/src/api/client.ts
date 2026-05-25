import { clearGuestSession, getGuestSessionHeader, saveGuestSession } from "../lib/guestSession";

const API_BASE = import.meta.env.VITE_API_URL || "";

export type Plan = "free" | "pro";

export interface SessionStatus {
  authenticated: boolean;
  is_guest: boolean;
  searches_today: number;
  searches_limit: number;
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

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[] | null;
  follow_up_questions: string[] | null;
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

export async function fetchSession(token: string | null): Promise<SessionStatus> {
  const res = await fetch(`${API_BASE}/api/auth/session`, {
    headers: apiHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to load session");
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

export async function devActivatePro(token: string): Promise<void> {
  await fetch(`${API_BASE}/api/payments/dev-activate`, {
    method: "POST",
    headers: apiHeaders(token),
    credentials: "include",
  });
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

export interface SSEHandlers {
  onThread?: (id: string) => void;
  onRoute?: (route: RouteInfo) => void;
  onSources?: (sources: Source[]) => void;
  onToken?: (text: string) => void;
  onFollowUps?: (questions: string[]) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
}

export interface UploadedFile {
  id: string;
  filename: string;
  size_bytes: number;
  excerpt: string;
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
    throw new Error((err as { detail?: string }).detail || "Upload failed");
  }
  return res.json();
}

export async function streamSearch(
  token: string | null,
  query: string,
  threadId: string | null,
  attachmentIds: string[],
  handlers: SSEHandlers,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/search`, {
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
          handlers.onSources?.(parsed.sources);
          break;
        case "token":
          handlers.onToken?.(parsed.text);
          break;
        case "follow_ups":
          handlers.onFollowUps?.(parsed.questions);
          break;
        case "done":
          handlers.onDone?.();
          break;
        case "error":
          handlers.onError?.(parsed.message);
          break;
      }
    }
  }
}
