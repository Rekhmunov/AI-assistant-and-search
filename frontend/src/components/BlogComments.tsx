import { FormEvent, useEffect, useState } from "react";
import { createBlogComment, fetchBlogComments, type BlogComment } from "../api/blog";

type Props = {
  slug: string;
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString("ru-RU");
  } catch {
    return iso;
  }
}

export function BlogComments({ slug }: Props) {
  const [items, setItems] = useState<BlogComment[]>([]);
  const [authorName, setAuthorName] = useState("");
  const [body, setBody] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      setItems(await fetchBlogComments(slug));
    } catch {
      setItems([]);
    }
  };

  useEffect(() => {
    void load();
  }, [slug]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setMsg("");
    try {
      await createBlogComment(slug, { author_name: authorName.trim(), body: body.trim() });
      setBody("");
      setMsg("Комментарий добавлен");
      await load();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Не удалось отправить");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="blog-comments">
      <h2 className="blog-comments-title">Комментарии</h2>
      {items.length === 0 ? (
        <p className="blog-muted">Пока нет комментариев.</p>
      ) : (
        <ul className="blog-comments-list">
          {items.map((c) => (
            <li key={c.id} className="blog-comment">
              <strong>{c.author_name}</strong>
              <span className="blog-comment-date">{formatDate(c.created_at)}</span>
              <p>{c.body}</p>
            </li>
          ))}
        </ul>
      )}
      <form className="blog-comment-form" onSubmit={submit}>
        <input
          className="blog-comment-input"
          placeholder="Ваше имя"
          value={authorName}
          onChange={(e) => setAuthorName(e.target.value)}
          required
          minLength={2}
          maxLength={120}
        />
        <textarea
          className="blog-comment-input"
          rows={4}
          placeholder="Комментарий"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          required
          minLength={2}
          maxLength={4000}
        />
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "Отправка…" : "Отправить"}
        </button>
        {msg && <p className="blog-muted">{msg}</p>}
      </form>
    </section>
  );
}
