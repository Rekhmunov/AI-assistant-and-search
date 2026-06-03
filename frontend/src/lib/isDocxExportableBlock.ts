/** Блоки ```txt / markdown и крупные текстовые — оферты, договоры в чате. */

const DOC_BLOCK_LANGS = new Set([
  "txt",
  "text",
  "plain",
  "markdown",
  "md",
  "document",
  "doc",
  "оферта",
  "offer",
]);

const CODE_LANGS = new Set([
  "js",
  "javascript",
  "ts",
  "typescript",
  "tsx",
  "jsx",
  "py",
  "python",
  "json",
  "html",
  "css",
  "sql",
  "sh",
  "bash",
  "shell",
  "php",
  "java",
  "go",
  "rust",
  "c",
  "cpp",
  "yaml",
  "yml",
  "xml",
]);

const MIN_CHARS = 80;

export function isDocxExportableBlock(
  code: string,
  lang: string | undefined,
  partial?: boolean,
): boolean {
  if (partial) return false;
  const text = code.trim();
  if (text.length < MIN_CHARS) return false;

  const l = (lang || "").trim().toLowerCase();
  if (l && CODE_LANGS.has(l)) return false;
  if (l && DOC_BLOCK_LANGS.has(l)) return true;

  if (!l && text.length >= 200) return true;

  if (/публичн\w*\s+оферт|оферт\w*\s+на\s+/i.test(text.slice(0, 500))) return true;

  return false;
}
