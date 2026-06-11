import { formatApiErrorDetail } from "./lib/apiErrorDetail";

const API = import.meta.env.VITE_API_URL || "";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

const HTTP_STATUS_RU: Record<number, string> = {
  400: "Некорректный запрос",
  401: "Необходима авторизация",
  403: "Доступ запрещён",
  404: "Не найдено",
  405: "Метод не поддерживается",
  408: "Превышено время ожидания",
  409: "Конфликт данных",
  413: "Файл слишком большой",
  422: "Ошибка валидации данных",
  429: "Слишком много запросов",
  500: "Внутренняя ошибка сервера",
  502: "Ошибка внешнего сервиса",
  503: "Сервис временно недоступен",
  504: "Превышено время ожидания шлюза",
};

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });

  if (!res.ok) {
    const fallback = HTTP_STATUS_RU[res.status] ?? res.statusText;
    let detail = fallback;
    try {
      const body = await res.json();
      detail = formatApiErrorDetail(body, fallback);
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  if (!res.ok) {
    const fallback = HTTP_STATUS_RU[res.status] ?? res.statusText;
    let detail = fallback;
    try {
      const body = await res.json();
      detail = formatApiErrorDetail(body, fallback);
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }

  return res.json() as Promise<T>;
}
