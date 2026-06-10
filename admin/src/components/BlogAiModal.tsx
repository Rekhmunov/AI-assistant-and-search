import { FormEvent, useState } from "react";
import { createPortal } from "react-dom";
import { apiFetch } from "../api";
import { AdminModal } from "./AdminModal";

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

type CoverResult = {
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
  defaultTopic?: string;
};

export function BlogAiModal({ open, onClose, onApplyArticle, onApplyCover, defaultTopic = "" }: Props) {
  const [topic, setTopic] = useState(defaultTopic);
  const [requirements, setRequirements] = useState("");
  const [coverPrompt, setCoverPrompt] = useState("");
  const [busy, setBusy] = useState<"article" | "cover" | null>(null);
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
      const data = await apiFetch<CoverResult>("/api/admin/blog/generate-cover", {
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

  return createPortal(
    <AdminModal title="AI: статья и обложка" onClose={onClose}>
      <form className="blog-ai-form" onSubmit={generateArticle}>
        <label className="field-label">
          Тема / заголовок
          <input
            className="field-input"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            required
            minLength={3}
            placeholder="Как ИИ-поиск экономит время"
          />
        </label>
        <label className="field-label">
          Требования к тексту
          <textarea
            className="field-input field-textarea"
            rows={4}
            value={requirements}
            onChange={(e) => setRequirements(e.target.value)}
            placeholder="Объём, тон, ключевые слова, структура разделов…"
          />
        </label>
        <label className="field-label">
          Промпт обложки (опционально)
          <input
            className="field-input"
            value={coverPrompt}
            onChange={(e) => setCoverPrompt(e.target.value)}
            placeholder="Минималистичная иллюстрация, бирюзовые тона…"
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <div className="blog-ai-actions">
          <button type="submit" className="btn-primary" disabled={busy !== null}>
            {busy === "article" ? "Генерация…" : "Сгенерировать статью"}
          </button>
          <button type="button" className="btn-secondary" disabled={busy !== null} onClick={generateCover}>
            {busy === "cover" ? "Генерация…" : "Сгенерировать обложку"}
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
