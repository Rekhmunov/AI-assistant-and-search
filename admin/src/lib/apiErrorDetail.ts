/** Текст ошибки из ответа FastAPI (detail: string | object[]). */
export function formatApiErrorDetail(body: unknown, fallback: string): string {
  if (typeof body === "string" && body.trim()) return body.trim();
  if (!body || typeof body !== "object") return fallback;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string" && detail.trim()) return detail.trim();
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const msg = (detail as { message?: string }).message;
    if (typeof msg === "string" && msg.trim()) return msg;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (!item || typeof item !== "object") return "";
        const row = item as { msg?: string; loc?: unknown[] };
        const msg = typeof row.msg === "string" ? row.msg : "";
        if (!msg) return "";
        const loc = Array.isArray(row.loc) ? row.loc.filter((x) => x !== "body").join(".") : "";
        return loc ? `${loc}: ${msg}` : msg;
      })
      .filter(Boolean);
    if (parts.length) return parts.join("; ");
  }
  return fallback;
}
