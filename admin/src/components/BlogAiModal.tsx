import { FormEvent, useState } from "react";
import { createPortal } from "react-dom";
import { apiFetch } from "../api";
import { AdminModal } from "./AdminModal";
import { GenerationStatusLine } from "./GenerationStatusLine";

type ArticleResult = {
  title: string;
  slug: string;
  excerpt: string;
  content_html: string;
  meta_title: string;
  meta_description: string;
  meta_keywords: string;
  og_title: string;
  og_description: string;
};

type MediaResult = {
  media: {
    id: string;
    url: string;
    alt_text: string;
  };
};

type Props = {
  open: boolean;
  onClose: () => void;
  onApplyArticle: (data: ArticleResult) => void;
  onApplyCover: (mediaId: string, url: string) => void;
  onApplyInlineImage: (url: string, altText: string) => void;
  defaultTopic?: string;
};

export function BlogAiModal({
  open,
  onClose,
  onApplyArticle,
  onApplyCover,
  onApplyInlineImage,
  defaultTopic = "",
}: Props) {
  const [topic, setTopic] = useState(defaultTopic);
  const [requirements, setRequirements] = useState("");
  const [coverPrompt, setCoverPrompt] = useState("");
  const [inlinePrompt, setInlinePrompt] = useState("");
  const [busy, setBusy] = useState<"article" | "cover" | "inline" | null>(null);
  const [error, setError] = useState("");

  if (!open) return null;

  const generateArticle = async (e: FormEvent) => {
    e.preventDefault();
    setBusy("article");
    setError("");
    try {
      const data = await apiFetch<ArticleResult>("/api/admin/blog/generate-article", {
        method: "POST",
        body: JSON.stringify({
          topic,
          requirements,
          fill_seo: true,
          generate_slug: true,
        }),
      });
      onApplyArticle(data);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка генерации");
    } finally {
      setBusy(null);
    }
  };

  const generateCover = async () => {
    const prompt = coverPrompt.trim() || topic.trim();
    if (!prompt) {
      setError("Укажите тему или промпт для обложки");
      return;
    }
    setBusy("cover");
    setError("");
    try {
      const data = await apiFetch<MediaResult>("/api/admin/blog/generate-cover", {
        method: "POST",
        body: JSON.stringify({ prompt, alt_text: topic.trim() }),
      });
      onApplyCover(data.media.id, data.media.url);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка генерации обложки");
    } finally {
      setBusy(null);
    }
  };

  const generateInlineImage = async () => {
    const prompt = inlinePrompt.trim();
    if (prompt.length < 3) {
      setError("Введите промпт для картинки (минимум 3 символа)");
      return;
    }
    setBusy("inline");
    setError("");
    try {
      const data = await apiFetch<MediaResult>("/api/admin/blog/generate-inline-image", {
        method: "POST",
        body: JSON.stringify({ prompt, alt_text: prompt.slice(0, 200) }),
      });
      onApplyInlineImage(data.media.url, data.media.alt_text || prompt.slice(0, 200));
      setInlinePrompt("");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка генерации изображения");
    } finally {
      setBusy(null);
    }
  };

  return createPortal(
    <AdminModal title="AI: статья, обложка и картинки" onClose={onClose}>
      <form className="blog-ai-form" onSubmit={generateArticle}>
        <label className="blog-field blog-field--wide">
          <span className="blog-field-label">Тема / заголовок</span>
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            required
            minLength={3}
            placeholder="Как ИИ-поиск экономит время"
          />
        </label>
        <label className="blog-field blog-field--wide">
          <span className="blog-field-label">Требования к тексту</span>
          <textarea
            rows={4}
            value={requirements}
            onChange={(e) => setRequirements(e.target.value)}
            placeholder="Объём, тон, ключевые слова, структура разделов…"
          />
        </label>
        <label className="blog-field blog-field--wide">
          <span className="blog-field-label">Промпт обложки (опционально)</span>
          <input
            value={coverPrompt}
            onChange={(e) => setCoverPrompt(e.target.value)}
            placeholder="Минималистичная иллюстрация, бирюзовые тона…"
          />
        </label>
        <label className="blog-field blog-field--wide">
          <span className="blog-field-label">Картинка в текст статьи</span>
          <input
            value={inlinePrompt}
            onChange={(e) => setInlinePrompt(e.target.value)}
            placeholder="Схема работы ИИ-поиска, плоский стиль, светлый фон…"
          />
          <span className="hint">
            Вставится в позицию курсора в редакторе (отметьте место перед открытием окна).
          </span>
        </label>
        {error && <p className="error">{error}</p>}
        {(busy === "cover" || busy === "inline") && <GenerationStatusLine active />}
        {busy === "article" && (
          <GenerationStatusLine active status="Составляем статью…" />
        )}
        <div className="blog-ai-actions">
          <button type="submit" className="btn-primary" disabled={busy !== null}>
            {busy === "article" ? "Генерация…" : "Сгенерировать статью"}
          </button>
          <button type="button" className="btn-secondary" disabled={busy !== null} onClick={generateCover}>
            {busy === "cover" ? "Генерация…" : "Сгенерировать обложку"}
          </button>
          <button type="button" className="btn-secondary" disabled={busy !== null} onClick={generateInlineImage}>
            {busy === "inline" ? "Генерация…" : "Вставить картинку в статью"}
          </button>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Отмена
          </button>
        </div>
      </form>
    </AdminModal>,
    document.body,
  );
}
