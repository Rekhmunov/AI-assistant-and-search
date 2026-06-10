import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiFetch, apiUpload } from "../api";
import { useAuth } from "../AuthContext";
import { BlogAiModal } from "../components/BlogAiModal";
import { BlogRichTextEditor } from "../components/BlogRichTextEditor";

const API = import.meta.env.VITE_API_URL || "";

type Category = { id: string; name: string; slug: string };

type PostForm = {
  title: string;
  slug: string;
  excerpt: string;
  content_html: string;
  status: string;
  category_id: string;
  cover_image_id: string;
  og_image_id: string;
  meta_title: string;
  meta_description: string;
  meta_keywords: string;
  og_title: string;
  og_description: string;
  robots_index: boolean;
  author_name: string;
  comments_enabled: boolean;
};

type AdminComment = {
  id: string;
  author_name: string;
  body: string;
  created_at: string;
};

const EMPTY: PostForm = {
  title: "",
  slug: "",
  excerpt: "",
  content_html: "<p></p>",
  status: "draft",
  category_id: "",
  cover_image_id: "",
  og_image_id: "",
  meta_title: "",
  meta_description: "",
  meta_keywords: "",
  og_title: "",
  og_description: "",
  robots_index: true,
  author_name: "",
  comments_enabled: false,
};

function mediaSrc(url: string | undefined): string {
  if (!url) return "";
  return url.startsWith("http") ? url : `${API}${url}`;
}

export function BlogEditPage() {
  const { id } = useParams();
  const isNew = id === "new";
  const navigate = useNavigate();
  const { can } = useAuth();
  const canWrite = can("blog:write");
  const [form, setForm] = useState<PostForm>(EMPTY);
  const [categories, setCategories] = useState<Category[]>([]);
  const [coverUrl, setCoverUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [aiOpen, setAiOpen] = useState(false);
  const [comments, setComments] = useState<AdminComment[]>([]);

  useEffect(() => {
    apiFetch<Category[]>("/api/admin/blog/categories").then(setCategories);
  }, []);

  useEffect(() => {
    if (isNew || !id) return;
    apiFetch<PostForm & { cover_image?: { url: string } }>(`/api/admin/blog/posts/${id}`).then((post) => {
      setForm({
        title: post.title,
        slug: post.slug,
        excerpt: post.excerpt,
        content_html: post.content_html,
        status: post.status,
        category_id: post.category_id || "",
        cover_image_id: post.cover_image_id || "",
        og_image_id: post.og_image_id || "",
        meta_title: post.meta_title,
        meta_description: post.meta_description,
        meta_keywords: post.meta_keywords,
        og_title: post.og_title,
        og_description: post.og_description,
        robots_index: post.robots_index,
        author_name: post.author_name || "",
        comments_enabled: post.comments_enabled || false,
      });
      setCoverUrl(post.cover_image?.url || "");
      apiFetch<AdminComment[]>(`/api/admin/blog/posts/${id}/comments`).then(setComments).catch(() => setComments([]));
    });
  }, [id, isNew]);

  const patch = (partial: Partial<PostForm>) => setForm((f) => ({ ...f, ...partial }));

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!canWrite) return;
    setBusy(true);
    setMsg("");
    const body = {
      ...form,
      category_id: form.category_id || null,
      cover_image_id: form.cover_image_id || null,
      og_image_id: form.og_image_id || null,
    };
    try {
      if (isNew) {
        const created = await apiFetch<{ id: string }>("/api/admin/blog/posts", {
          method: "POST",
          body: JSON.stringify(body),
        });
        navigate(`/blog/${created.id}`, { replace: true });
        setMsg("Создано");
      } else {
        await apiFetch(`/api/admin/blog/posts/${id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
        setMsg("Сохранено");
      }
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Ошибка сохранения");
    } finally {
      setBusy(false);
    }
  };

  const uploadCover = async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const media = await apiUpload<{ id: string; url: string }>(
      "/api/admin/blog/media?purpose=cover",
      formData,
    );
    patch({ cover_image_id: media.id, og_image_id: form.og_image_id || media.id });
    setCoverUrl(media.url);
  };

  return (
    <div className="page blog-edit-page">
      <div className="page-header-row">
        <h1>{isNew ? "Новая статья" : "Редактирование статьи"}</h1>
        <div className="blog-edit-header-actions">
          {canWrite && (
            <button type="button" className="btn-secondary" onClick={() => setAiOpen(true)}>
              ✨ AI-черновик
            </button>
          )}
          <Link to="/blog" className="btn-secondary">
            ← К списку
          </Link>
        </div>
      </div>
      <form className="blog-edit-form" onSubmit={save}>
        <div className="blog-edit-grid">
          <section className="blog-edit-main">
            <label className="field-label">
              Заголовок
              <input
                className="field-input"
                value={form.title}
                onChange={(e) => patch({ title: e.target.value })}
                required
                disabled={!canWrite}
              />
            </label>
            <label className="field-label">
              Slug (латиница, URL: /blog/…)
              <input
                className="field-input"
                value={form.slug}
                onChange={(e) => patch({ slug: e.target.value })}
                placeholder="auto-from-title"
                disabled={!canWrite}
              />
            </label>
            <label className="field-label">
              Автор (ФИО)
              <input
                className="field-input"
                value={form.author_name}
                onChange={(e) => patch({ author_name: e.target.value })}
                placeholder="Иван Иванов"
                disabled={!canWrite}
              />
            </label>
            <label className="field-label">
              Краткое описание
              <textarea
                className="field-input field-textarea"
                rows={2}
                value={form.excerpt}
                onChange={(e) => patch({ excerpt: e.target.value })}
                disabled={!canWrite}
              />
            </label>
            <label className="field-label">Текст статьи</label>
            <BlogRichTextEditor
              value={form.content_html}
              onChange={(html) => patch({ content_html: html })}
              disabled={!canWrite}
            />
          </section>
          <aside className="blog-edit-side">
            <label className="field-label">
              Статус
              <select
                className="field-input"
                value={form.status}
                onChange={(e) => patch({ status: e.target.value })}
                disabled={!canWrite}
              >
                <option value="draft">Черновик</option>
                <option value="published">Опубликовано</option>
                <option value="archived">Архив</option>
              </select>
            </label>
            <label className="field-label">
              Категория
              <select
                className="field-input"
                value={form.category_id}
                onChange={(e) => patch({ category_id: e.target.value })}
                disabled={!canWrite}
              >
                <option value="">—</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="field-label">
              Обложка
              {coverUrl && (
                <img src={mediaSrc(coverUrl)} alt="" className="blog-cover-preview" />
              )}
              {canWrite && (
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) void uploadCover(f).catch((err) => setMsg(String(err)));
                  }}
                />
              )}
            </div>
            <h3 className="blog-seo-title">SEO</h3>
            <label className="field-label">
              Meta title
              <input className="field-input" value={form.meta_title} onChange={(e) => patch({ meta_title: e.target.value })} disabled={!canWrite} />
            </label>
            <label className="field-label">
              Meta description
              <textarea className="field-input field-textarea" rows={2} value={form.meta_description} onChange={(e) => patch({ meta_description: e.target.value })} disabled={!canWrite} />
            </label>
            <label className="field-label">
              Keywords
              <input className="field-input" value={form.meta_keywords} onChange={(e) => patch({ meta_keywords: e.target.value })} disabled={!canWrite} />
            </label>
            <label className="field-label">
              OG title
              <input className="field-input" value={form.og_title} onChange={(e) => patch({ og_title: e.target.value })} disabled={!canWrite} />
            </label>
            <label className="field-label">
              OG description
              <textarea className="field-input field-textarea" rows={2} value={form.og_description} onChange={(e) => patch({ og_description: e.target.value })} disabled={!canWrite} />
            </label>
            <label className="field-label checkbox-label">
              <input
                type="checkbox"
                checked={form.robots_index}
                onChange={(e) => patch({ robots_index: e.target.checked })}
                disabled={!canWrite}
              />
              Индексировать (robots index)
            </label>
            <label className="field-label checkbox-label">
              <input
                type="checkbox"
                checked={form.comments_enabled}
                onChange={(e) => patch({ comments_enabled: e.target.checked })}
                disabled={!canWrite}
              />
              Комментарии к статье
            </label>
            {!isNew && comments.length > 0 && (
              <div className="blog-admin-comments">
                <h3 className="blog-seo-title">Комментарии ({comments.length})</h3>
                <ul className="blog-admin-comments-list">
                  {comments.map((c) => (
                    <li key={c.id}>
                      <strong>{c.author_name}</strong>
                      <p>{c.body}</p>
                      {canWrite && (
                        <button
                          type="button"
                          className="btn-link btn-link--danger"
                          onClick={async () => {
                            if (!window.confirm("Удалить комментарий?")) return;
                            await apiFetch(`/api/admin/blog/posts/${id}/comments/${c.id}`, { method: "DELETE" });
                            setComments((prev) => prev.filter((x) => x.id !== c.id));
                          }}
                        >
                          Удалить
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </aside>
        </div>
        {msg && <p className="form-msg">{msg}</p>}
        {canWrite && (
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? "Сохранение…" : "Сохранить"}
          </button>
        )}
      </form>
      <BlogAiModal
        open={aiOpen}
        onClose={() => setAiOpen(false)}
        defaultTopic={form.title}
        onApplyArticle={(data) => {
          patch({
            title: data.title,
            slug: data.slug,
            excerpt: data.excerpt,
            content_html: data.content_html,
            meta_title: data.meta_title,
            meta_description: data.meta_description,
            meta_keywords: data.meta_keywords,
            og_title: data.og_title,
            og_description: data.og_description,
          });
        }}
        onApplyCover={(mediaId, url) => {
          patch({ cover_image_id: mediaId, og_image_id: mediaId });
          setCoverUrl(url);
        }}
      />
    </div>
  );
}
