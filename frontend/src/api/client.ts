const API_BASE = import.meta.env.VITE_API_URL || "";

export type Plan = "free" | "pro";

export interface UserProfile {
  id: string;
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

function authHeaders(token: string | null): HeadersInit {
  const h: HeadersInit = { "Content-Type": "application/json" };
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

export async function login(initData: string): Promise<{ access_token: string; user: UserProfile }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ init_data: initData }),
  });
  if (!res.ok) throw new Error("Auth failed");
  return res.json();
}

export async function fetchMe(token: string): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/api/users/me`, {
    headers: authHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to load profile");
  return res.json();
}

export async function fetchThreads(token: string): Promise<ThreadListItem[]> {
  const res = await fetch(`${API_BASE}/api/threads`, {
    headers: authHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to load threads");
  return res.json();
}

export async function fetchThread(token: string, id: string): Promise<ThreadDetail> {
  const res = await fetch(`${API_BASE}/api/threads/${id}`, {
    headers: authHeaders(token),
    credentials: "include",
  });
  if (!res.ok) throw new Error("Failed to load thread");
  return res.json();
}

export async function saveThread(token: string, id: string): Promise<void> {
  await fetch(`${API_BASE}/api/threads/${id}/save`, {
    method: "POST",
    headers: authHeaders(token),
    credentials: "include",
  });
}

export async function devActivatePro(token: string): Promise<void> {
  await fetch(`${API_BASE}/api/payments/dev-activate`, {
    method: "POST",
    headers: authHeaders(token),
    credentials: "include",
  });
}

export async function deleteAccount(token: string): Promise<void> {
  await fetch(`${API_BASE}/api/users/me`, {
    method: "DELETE",
    headers: authHeaders(token),
    credentials: "include",
  });
}

export interface SSEHandlers {
  onThread?: (id: string) => void;
  onSources?: (sources: Source[]) => void;
  onToken?: (text: string) => void;
  onFollowUps?: (questions: string[]) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
}

export async function streamSearch(
  token: string,
  query: string,
  threadId: string | null,
  handlers: SSEHandlers,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/search`, {
    method: "POST",
    headers: authHeaders(token),
    credentials: "include",
    body: JSON.stringify({ query, thread_id: threadId }),
    signal,
  });

  if (!res.ok || !res.body) {
    handlers.onError?.("Ошибка поиска");
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
