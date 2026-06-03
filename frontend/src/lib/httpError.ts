/** Ошибка HTTP-запроса с кодом ответа (для различения 401 и 502). */
export class HttpResponseError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "HttpResponseError";
    this.status = status;
  }
}

export function isAuthFailureStatus(status: number): boolean {
  return status === 401 || status === 403;
}

export function isTransientFailureStatus(status: number): boolean {
  return status === 0 || status === 502 || status === 503 || status === 504;
}
