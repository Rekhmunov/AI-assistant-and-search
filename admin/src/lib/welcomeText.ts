const HTML_TAG_RE = /<[a-z][\s\S]*>/i;

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** Преобразовать сохранённый plain/HTML текст в HTML для редактора. */
export function welcomeTextToEditorHtml(text: string): string {
  if (!text.trim()) return "<p></p>";
  if (HTML_TAG_RE.test(text)) return text;
  return text
    .split(/\n\n+/)
    .map((paragraph) => `<p>${escapeHtml(paragraph).replace(/\n/g, "<br>")}</p>`)
    .join("");
}

export function isWelcomeHtmlEmpty(html: string): boolean {
  if (!html.trim()) return true;
  const div = document.createElement("div");
  div.innerHTML = html;
  return !(div.textContent || "").trim();
}
