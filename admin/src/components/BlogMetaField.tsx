import { useState } from "react";
import { apiFetch } from "../api";

export type MetaFieldKey =
  | "meta_title"
  | "meta_description"
  | "meta_keywords"
  | "og_title"
  | "og_description";

const META_SPECS: Record<
  MetaFieldKey,
  { label: string; max: number; min: number; hint: string; multiline?: boolean }
> = {
  meta_title: {
    label: "Meta title",
    max: 55,
    min: 30,
    hint: "Яндекс/Google: 50–55 символов, ключ в начале",
  },
  meta_description: {
    label: "Meta description",
    max: 155,
    min: 120,
    hint: "Google: 120–155 символов",
    multiline: true,
  },
  meta_keywords: {
    label: "Keywords",
    max: 100,
    min: 20,
    hint: "5–8 фраз через запятую",
  },
  og_title: {
    label: "OG title",
    max: 60,
    min: 30,
    hint: "Для соцсетей, до 60 символов",
  },
  og_description: {
    label: "OG description",
    max: 200,
    min: 80,
    hint: "Превью в соцсетях, до 200 символов",
    multiline: true,
  },
};

type Props = {
  field: MetaFieldKey;
  value: string;
  onChange: (value: string) => void;
  articleTitle: string;
  excerpt: string;
  contentHtml: string;
  canWrite?: boolean;
  disabled?: boolean;
};

function counterClass(len: number, min: number, max: number): string {
  if (len > max) return "blog-meta-counter blog-meta-counter--over";
  if (len < min && len > 0) return "blog-meta-counter blog-meta-counter--short";
  if (len >= min && len <= max) return "blog-meta-counter blog-meta-counter--ok";
  return "blog-meta-counter";
}

export function BlogMetaField({
  field,
  value,
  onChange,
  articleTitle,
  excerpt,
  contentHtml,
  canWrite = false,
  disabled,
}: Props) {
  const spec = META_SPECS[field];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const generate = async () => {
    if (!articleTitle.trim()) {
      setError("Сначала укажите заголовок статьи");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const data = await apiFetch<{ value: string }>("/api/admin/blog/generate-meta", {
        method: "POST",
        body: JSON.stringify({
          field,
          title: articleTitle,
          excerpt,
          content_html: contentHtml,
        }),
      });
      onChange(data.value);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка генерации");
    } finally {
      setBusy(false);
    }
  };

  const len = value.length;

  return (
    <div className="blog-field blog-meta-field">
      <div className="blog-meta-field-head">
        <span className="blog-field-label">{spec.label}</span>
        <span className={counterClass(len, spec.min, spec.max)}>
          {len}/{spec.max}
        </span>
      </div>
      <span className="hint blog-meta-hint">{spec.hint}</span>
      {spec.multiline ? (
        <textarea
          rows={3}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled || busy}
          maxLength={spec.max + 20}
        />
      ) : (
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled || busy}
          maxLength={spec.max + 10}
        />
      )}
      {canWrite && !disabled && (
        <button
          type="button"
          className="btn-secondary btn-secondary--compact blog-meta-generate-btn"
          disabled={busy}
          onClick={() => void generate()}
        >
          {busy ? "Генерация…" : "Сгенерировать"}
        </button>
      )}
      {error && <span className="blog-meta-error">{error}</span>}
    </div>
  );
}
