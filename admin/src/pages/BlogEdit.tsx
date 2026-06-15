import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { apiFetch, apiUpload } from "../api";
import { useAuth } from "../AuthContext";
import { BlogAiModal } from "../components/BlogAiModal";
import { BlogMetaField } from "../components/BlogMetaField";
import { BlogRichTextEditor, type BlogRichTextEditorHandle } from "../components/BlogRichTextEditor";

const API = import.meta.env.VITE_API_URL || "";
const PUBLIC_SITE = import.meta.env.VITE_PUBLIC_URL || "https://glosix.ru";

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

function formatCommentDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ru-RU");
  } catch {
    return iso;
  }
}

function PanelChevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`blog-panel-chevron${expanded ? " blog-panel-chevron--expanded" : ""}`}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

type PostAdminResponse = PostForm & { cover_image?: { url: string } | null };

export function BlogEditPage() {
  const { id } = useParams();
  const isNew = !id || id === "new";
  const navigate = useNavigate();
  const location = useLocation();
  const { can } = useAuth();
  const canWrite = can("blog:write");
  const [form, setForm] = useState<PostForm>(EMPTY);
  const [categories, setCategories] = useState<Category[]>([]);
  const [coverUrl, setCoverUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [coverBusy, setCoverBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [aiOpen, setAiOpen] = useState(false);
  const [comments, setComments] = useState<AdminComment[]>([]);
  const [seoOpen, setSeoOpen] = useState(false);
  const editorRef = useRef<BlogRichTextEditorHandle>(null);

  // Show success message passed via navigation state (e.g. "Статья создана" after redirect)
  useEffect(() => {
    const state = location.state as { msg?: string } | null;
    if (state?.msg) {
      setMsg(state.msg);
      window.history.replaceState({}, "");
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    apiFetch<Category[]>("/api/admin/blog/categories")
      .then(setCategories)
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Не удалось загрузить категории");
      });
  }, []);

  const applyPostToForm = (post: PostAdminResponse) => {
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
  };

  useEffect(() => {
    if (isNew || !id) return;
    setError("");
    apiFetch<PostAdminResponse>(`/api/admin/blog/posts/${id}`)
      .then((post) => {
        applyPostToForm(post);
        apiFetch<AdminComment[]>(`/api/admin/blog/posts/${id}/comments`).then(setComments).catch(() => setComments([]));
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Не удалось загрузить статью");
      });
  }, [id, isNew]); // eslint-disable-line react-hooks/exhaustive-deps

  const patch = (partial: Partial<PostForm>) => setForm((f) => ({ ...f, ...partial }));

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!canWrite) return;
    setBusy(true);
    setMsg("");
    setError("");
    const body: Record<string, unknown> = {
      ...form,
      category_id: form.category_id || null,
      cover_image_id: form.cover_image_id || null,
      og_image_id: form.og_image_id || null,
    };
    if (!isNew && !form.slug.trim()) {
      delete body.slug;
    } else if (!form.slug.trim()) {
      body.slug = null;
    }
    try {
      if (isNew) {
        const created = await apiFetch<{ id: string }>("/api/admin/blog/posts", {
          method: "POST",
          body: JSON.stringify(body),
        });
        navigate(`/blog/${created.id}`, { replace: true, state: { msg: "Статья создана" } });
      } else {
        const saved = await apiFetch<PostAdminResponse>(`/api/admin/blog/posts/${id}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
        // Sync form with server response (reflects sanitized HTML, updated timestamps, etc.)
        applyPostToForm(saved);
        setMsg("Сохранено");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка сохранения");
    } finally {
      setBusy(false);
    }
  };

  const uploadCover = async (file: File) => {
    setCoverBusy(true);
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      const media = await apiUpload<{ id: string; url: string }>(
        "/api/admin/blog/media?purpose=cover",
        formData,
      );
      patch({ cover_image_id: media.id, og_image_id: form.og_image_id || media.id });
      setCoverUrl(media.url);
      setMsg("Обложка загружена");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить обложку");
    } finally {
      setCoverBusy(false);
    }
  };

  const clearCover = () => {
    patch({ cover_image_id: "", og_image_id: "" });
    setCoverUrl("");
  };

  const publicUrl = form.slug ? `${PUBLIC_SITE}/blog/${form.slug}` : "";

  return (
    <div className="admin-page admin-page--blog-edit">
      <header className="admin-page-header">
        <div>
          <h1>{isNew ? "Новая статья" : "Редактирование статьи"}</h1>
          <p className="admin-page-subtitle">
            {isNew
              ? "Заполните заголовок и текст, затем опубликуйте в боковой панели."
              : form.slug
                ? `URL: /blog/${form.slug}`
                : "Черновик без slug"}
          </p>
        </div>
        <div className="blog-edit-header-actions">
          {canWrite && (
            <button
              type="button"
              className="btn-secondary"
              onMouseDown={(e) => {
                e.preventDefault();
                editorRef.current?.markCaret();
              }}
              onClick={() => setAiOpen(true)}
            >
              AI-черновик
            </button>
          )}
          {form.status === "published" && publicUrl && (
            <a className="btn-secondary" href={publicUrl} target="_blank" rel="noreferrer">
              На сайте ↗
            </a>
          )}
          <Link to="/blog" className="btn-secondary">
            К списку
          </Link>
        </div>
      </header>

      {msg && <p className="ok card">{msg}</p>}
      {error && <p className="error card">{error}</p>}

      <form className="blog-edit-layout" onSubmit={save}>
        <div className="blog-edit-main">
          <section className="card blog-edit-section">
            <h2 className="blog-section-title">Основное</h2>
            <div className="blog-fields-grid">
              <label className="blog-field blog-field--wide">
                <span className="blog-field-label">Заголовок</span>
                <input
                  value={form.title}
                  onChange={(e) => patch({ title: e.target.value })}
                  required
                  disabled={!canWrite}
                  placeholder="Заголовок статьи"
                />
              </label>
              <label className="blog-field">
                <span className="blog-field-label">Slug (латиница)</span>
                <input
                  value={form.slug}
                  onChange={(e) => patch({ slug: e.target.value })}
                  placeholder="auto-from-title"
                  disabled={!canWrite}
                />
              </label>
              <label className="blog-field">
                <span className="blog-field-label">Автор (ФИО)</span>
                <input
                  value={form.author_name}
                  onChange={(e) => patch({ author_name: e.target.value })}
                  placeholder="Иван Иванов"
                  disabled={!canWrite}
                />
              </label>
              <label className="blog-field blog-field--wide">
                <span className="blog-field-label">Краткое описание</span>
                <textarea
                  rows={3}
                  value={form.excerpt}
                  onChange={(e) => patch({ excerpt: e.target.value })}
                  disabled={!canWrite}
                  placeholder="Анонс для списка статей и соцсетей"
                />
              </label>
            </div>
          </section>

          <section className="card blog-edit-section">
            <h2 className="blog-section-title">Текст статьи</h2>
            <BlogRichTextEditor
              ref={editorRef}
              value={form.content_html}
              onChange={(html) => patch({ content_html: html })}
              disabled={!canWrite}
            />
          </section>
        </div>

        <aside className="blog-edit-sidebar">
          <section className="card blog-panel">
            <h3 className="blog-panel-title">Публикация</h3>
            <label className="blog-field">
              <span className="blog-field-label">Статус</span>
              <select
                value={form.status}
                onChange={(e) => patch({ status: e.target.value })}
                disabled={!canWrite}
              >
                <option value="draft">Черновик</option>
                <option value="published">Опубликовано</option>
                <option value="archived">Архив</option>
              </select>
            </label>
            <label className="blog-field">
              <span className="blog-field-label">Категория</span>
              <select
                value={form.category_id}
                onChange={(e) => patch({ category_id: e.target.value })}
                disabled={!canWrite}
              >
                <option value="">Без категории</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="blog-toggle">
              <input
                type="checkbox"
                checked={form.comments_enabled}
                onChange={(e) => patch({ comments_enabled: e.target.checked })}
                disabled={!canWrite}
              />
              <span>Комментарии к статье</span>
            </label>
          </section>

          <section className="card blog-panel">
            <h3 className="blog-panel-title">Обложка</h3>
            <div className="blog-cover-block">
              {coverUrl ? (
                <img src={mediaSrc(coverUrl)} alt="" className="blog-cover-preview" />
              ) : (
                <div className="blog-cover-placeholder">16:9</div>
              )}
              {canWrite && (
                <div className="blog-cover-actions">
                  <label className="btn-secondary blog-file-btn">
                    {coverBusy ? "Загрузка…" : coverUrl ? "Заменить" : "Загрузить"}
                    <input
                      type="file"
                      accept="image/jpeg,image/png,image/webp,image/gif"
                      hidden
                      disabled={coverBusy}
                      onChange={(e) => {
                        const f = e.target.files?.[0];
                        e.target.value = "";
                        if (f) void uploadCover(f);
                      }}
                    />
                  </label>
                  {coverUrl && (
                    <button type="button" className="btn-secondary btn-danger-outline" onClick={clearCover}>
                      Убрать
                    </button>
                  )}
                </div>
              )}
              <p className="hint blog-cover-hint">JPEG, PNG, WebP — сжимается в WebP при загрузке</p>
            </div>
          </section>

          <section className="card blog-panel blog-panel--collapsible">
            <button
              type="button"
              className="blog-panel-toggle"
              onClick={() => setSeoOpen((v) => !v)}
              aria-expanded={seoOpen}
            >
              <span>SEO и Open Graph</span>
              <PanelChevron expanded={seoOpen} />
            </button>
            {seoOpen && (
              <div className="blog-panel-body">
                <BlogMetaField
                  field="meta_title"
                  value={form.meta_title}
                  onChange={(v) => patch({ meta_title: v })}
                  articleTitle={form.title}
                  excerpt={form.excerpt}
                  contentHtml={form.content_html}
                  canWrite={canWrite}
                  disabled={!canWrite}
                />
                <BlogMetaField
                  field="meta_description"
                  value={form.meta_description}
                  onChange={(v) => patch({ meta_description: v })}
                  articleTitle={form.title}
                  excerpt={form.excerpt}
                  contentHtml={form.content_html}
                  canWrite={canWrite}
                  disabled={!canWrite}
                />
                <BlogMetaField
                  field="meta_keywords"
                  value={form.meta_keywords}
                  onChange={(v) => patch({ meta_keywords: v })}
                  articleTitle={form.title}
                  excerpt={form.excerpt}
                  contentHtml={form.content_html}
                  canWrite={canWrite}
                  disabled={!canWrite}
                />
                <BlogMetaField
                  field="og_title"
                  value={form.og_title}
                  onChange={(v) => patch({ og_title: v })}
                  articleTitle={form.title}
                  excerpt={form.excerpt}
                  contentHtml={form.content_html}
                  canWrite={canWrite}
                  disabled={!canWrite}
                />
                <BlogMetaField
                  field="og_description"
                  value={form.og_description}
                  onChange={(v) => patch({ og_description: v })}
                  articleTitle={form.title}
                  excerpt={form.excerpt}
                  contentHtml={form.content_html}
                  canWrite={canWrite}
                  disabled={!canWrite}
                />
                <label className="blog-toggle">
                  <input
                    type="checkbox"
                    checked={form.robots_index}
                    onChange={(e) => patch({ robots_index: e.target.checked })}
                    disabled={!canWrite}
                  />
                  <span>Индексировать в поиске</span>
                </label>
              </div>
            )}
          </section>

          {!isNew && comments.length > 0 && (
            <section className="card blog-panel">
              <h3 className="blog-panel-title">Комментарии ({comments.length})</h3>
              <ul className="blog-admin-comments-list">
                {comments.map((c) => (
                  <li key={c.id} className="blog-admin-comment">
                    <div className="blog-admin-comment-head">
                      <strong>{c.author_name}</strong>
                      <span className="hint">{formatCommentDate(c.created_at)}</span>
                    </div>
                    <p>{c.body}</p>
                    {canWrite && (
                      <button
                        type="button"
                        className="blog-comment-delete"
                        onClick={async () => {
                          if (!window.confirm("Удалить комментарий?")) return;
                          try {
                            await apiFetch(`/api/admin/blog/posts/${id}/comments/${c.id}`, { method: "DELETE" });
                            setComments((prev) => prev.filter((x) => x.id !== c.id));
                          } catch (err) {
                            setError(err instanceof Error ? err.message : "Не удалось удалить комментарий");
                          }
                        }}
                      >
                        Удалить
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {canWrite && (
            <div className="blog-edit-save-bar card">
              <button type="submit" className="btn-primary blog-save-btn" disabled={busy}>
                {busy ? "Сохранение…" : isNew ? "Создать статью" : "Сохранить"}
              </button>
            </div>
          )}
        </aside>
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
          setSeoOpen(true);
          setMsg("AI-черновик подставлен — проверьте и сохраните");
        }}
        onApplyCover={(mediaId, url) => {
          patch({ cover_image_id: mediaId, og_image_id: mediaId });
          setCoverUrl(url);
          setMsg("Обложка от AI загружена");
        }}
        onApplyInlineImage={(url, altText) => {
          const src = mediaSrc(url);
          const imgHtml = `<p><img src="${src}" alt="${altText.replace(/"/g, "&quot;")}" title="${altText.replace(/"/g, "&quot;")}" loading="lazy" style="max-width:100%;height:auto;border-radius:8px;display:block;margin-left:auto;margin-right:auto;" /></p>`;
          const inserted = editorRef.current?.insertImageHtml(imgHtml);
          setMsg(
            inserted
              ? "Картинка вставлена в статью — сохраните изменения"
              : "Картинка добавлена в конец статьи — сохраните изменения",
          );
        }}
      />
    </div>
  );
}
