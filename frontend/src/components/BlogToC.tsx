import { useEffect, useRef, useState } from "react";

type TocItem = { id: string; text: string; level: 2 | 3 };

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^а-яёa-z0-9\s-]/gi, "")
    .trim()
    .replace(/\s+/g, "-");
}

function extractToc(contentHtml: string): TocItem[] {
  const div = document.createElement("div");
  div.innerHTML = contentHtml;
  const items: TocItem[] = [];
  div.querySelectorAll("h2, h3").forEach((el) => {
    const level = el.tagName === "H2" ? 2 : 3;
    const text = el.textContent?.trim() || "";
    if (!text) return;
    const id = el.id || slugify(text);
    items.push({ id, text, level });
  });
  return items;
}

function injectIds(contentHtml: string): string {
  return contentHtml.replace(/<(h[23])([^>]*)>([\s\S]*?)<\/\1>/gi, (match, tag, attrs, inner) => {
    const text = inner.replace(/<[^>]+>/g, "").trim();
    if (!text) return match;
    if (/id=["']/.test(attrs)) return match;
    const id = slugify(text);
    return `<${tag}${attrs} id="${id}">${inner}</${tag}>`;
  });
}

type Props = { contentHtml: string; onProcessed?: (html: string) => void };

export function BlogToC({ contentHtml, onProcessed }: Props) {
  const [items, setItems] = useState<TocItem[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const processed = useRef(false);

  useEffect(() => {
    const toc = extractToc(contentHtml);
    setItems(toc);
    if (!processed.current && onProcessed && toc.length > 0) {
      processed.current = true;
      onProcessed(injectIds(contentHtml));
    }
  }, [contentHtml, onProcessed]);

  useEffect(() => {
    if (items.length === 0) return;
    const ids = items.map((i) => i.id);
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (visible.length > 0) {
          setActiveId(visible[0].target.id);
        }
      },
      { rootMargin: "0px 0px -60% 0px", threshold: 0 },
    );
    ids.forEach((id) => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, [items]);

  if (items.length < 2) return null;

  return (
    <nav className="blog-toc" aria-label="Оглавление">
      <div className="blog-toc__title">Содержание</div>
      <ol className="blog-toc__list">
        {items.map((item) => (
          <li
            key={item.id}
            className={`blog-toc__item blog-toc__item--h${item.level}${activeId === item.id ? " blog-toc__item--active" : ""}`}
          >
            <a href={`#${item.id}`} className="blog-toc__link">
              {item.text}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  );
}
