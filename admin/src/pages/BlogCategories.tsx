import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import { useAuth } from "../AuthContext";

type Category = {
  id: string;
  slug: string;
  name: string;
  description: string;
};

export function BlogCategoriesPage() {
  const { can } = useAuth();
  const canWrite = can("blog:write");
  const [items, setItems] = useState<Category[]>([]);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [msg, setMsg] = useState("");

  const load = () => apiFetch<Category[]>("/api/admin/blog/categories").then(setItems);

  useEffect(() => {
    void load();
  }, []);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (!canWrite) return;
    setMsg("");
    try {
      await apiFetch("/api/admin/blog/categories", {
        method: "POST",
        body: JSON.stringify({ name, slug: slug.trim() || undefined, description: "" }),
      });
      setName("");
      setSlug("");
      setMsg("Категория создана");
      load();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "Ошибка");
    }
  };

  return (
    <div className="page">
      <div className="page-header-row">
        <h1>Категории блога</h1>
        <Link to="/blog" className="btn-secondary">
          ← К статьям
        </Link>
      </div>
      {canWrite && (
        <form className="blog-cat-form" onSubmit={create}>
          <input className="field-input" placeholder="Название" value={name} onChange={(e) => setName(e.target.value)} required />
          <input
            className="field-input"
            placeholder="slug (латиница, опционально)"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
          />
          <button type="submit" className="btn-primary">
            Добавить
          </button>
        </form>
      )}
      {msg && <p className="form-msg">{msg}</p>}
      <ul className="blog-cat-list">
        {items.map((c) => (
          <li key={c.id}>
            <strong>{c.name}</strong> <code>{c.slug}</code>
          </li>
        ))}
      </ul>
    </div>
  );
}
