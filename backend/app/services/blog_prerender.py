"""Static HTML prerender for blog pages (SEO)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, BaseLoader, select_autoescape
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.blog_comments import list_approved_comments
from app.services.blog_posts import (
    DEFAULT_LOCALE,
    blog_canonical_path,
    blog_media_url,
    get_category_by_slug,
    get_post_by_slug,
    list_categories,
    list_posts_public,
    media_out,
    post_to_public,
    resolve_slug_redirect,
)

logger = logging.getLogger(__name__)

_BLOG_CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:#1a2b32;background:#f7fafb;line-height:1.6}
.wrap{max-width:720px;margin:0 auto;padding:24px 16px 48px}
.wrap--wide{max-width:960px}
a{color:#20808d;text-decoration:none}a:hover{text-decoration:underline}
.muted{color:#5c6b73;font-size:.9rem}
.breadcrumbs{font-size:.88rem;margin-bottom:16px;color:#5c6b73}
h1{font-size:clamp(1.5rem,4vw,2rem);line-height:1.25;margin:0 0 10px}
.lead{margin:0 0 24px;color:#5c6b73}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px}
.card{border:1px solid #d8e0e3;border-radius:12px;overflow:hidden;background:#fff}
.card img{width:100%;aspect-ratio:16/9;object-fit:cover;background:#eef3f4}
.card-body{padding:14px 16px}
.card h2{font-size:1.1rem;margin:0 0 8px}
.cover{width:100%;border-radius:12px;margin:20px 0;aspect-ratio:16/9;object-fit:cover}
.prose h2{margin:1.6em 0 .6em;font-size:1.35rem}
.prose h3{margin:1.2em 0 .5em;font-size:1.15rem}
.prose p{margin:0 0 1em}
.prose img{max-width:100%;height:auto;border-radius:8px}
.prose ul,.prose ol{margin:0 0 1em;padding-left:1.4em}
.footer{margin-top:40px;padding-top:24px;border-top:1px solid #d8e0e3;display:flex;gap:12px;flex-wrap:wrap}
.btn{display:inline-block;padding:10px 16px;border-radius:8px;font-weight:600}
.btn-primary{background:#20808d;color:#fff}
.btn-secondary{border:1px solid #d8e0e3;color:#1a2b32;background:#fff}
.comments{margin-top:40px;padding-top:24px;border-top:1px solid #d8e0e3}
.comment{padding:12px 0;border-bottom:1px solid #e8eef0}
.comment strong{display:block;margin-bottom:4px}
.comment-form{display:flex;flex-direction:column;gap:8px;margin-top:16px}
.comment-form input,.comment-form textarea{padding:10px;border:1px solid #d8e0e3;border-radius:8px;font:inherit}
.blog-try-search{margin-top:40px;padding:24px 20px;border-radius:12px;border:1px solid #d8e0e3;background:linear-gradient(180deg,#f7fafb 0%,#fff 100%)}
.blog-try-search h2{margin:0 0 8px;font-size:1.2rem;line-height:1.3}
.blog-try-search-lead{margin:0 0 16px;color:#5c6b73;font-size:.95rem;line-height:1.5}
.blog-try-search-form{display:flex;flex-wrap:wrap;gap:10px;align-items:stretch}
.blog-try-search-form input{flex:1 1 220px;min-width:0;padding:12px 14px;border:1px solid #d8e0e3;border-radius:10px;font:inherit}
.blog-try-search-form input:focus{outline:none;border-color:#20808d;box-shadow:0 0 0 3px rgba(32,128,141,.12)}
.blog-try-search-form button{padding:12px 20px;border:none;border-radius:10px;background:#20808d;color:#fff;font:inherit;font-weight:600;cursor:pointer}
.blog-try-search-form button:hover{background:#1a6b76}
.cat-chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:24px}
.cat-chip{padding:6px 12px;border-radius:999px;border:1px solid #d8e0e3;font-size:.9rem}
"""

_POST_TEMPLATE = """<!DOCTYPE html>
<html lang="{{ locale }}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ meta_title }} — Glosix</title>
  <meta name="description" content="{{ meta_description }}" />
  {% if meta_keywords %}<meta name="keywords" content="{{ meta_keywords }}" />{% endif %}
  <link rel="canonical" href="{{ canonical_url }}" />
  <meta property="og:type" content="article" />
  <meta property="og:title" content="{{ og_title }}" />
  <meta property="og:description" content="{{ og_description }}" />
  <meta property="og:url" content="{{ canonical_url }}" />
  {% if og_image %}<meta property="og:image" content="{{ og_image }}" />{% endif %}
  <meta name="twitter:card" content="summary_large_image" />
  {% if not robots_index %}<meta name="robots" content="noindex, nofollow" />{% endif %}
  <script type="application/ld+json">{{ json_ld | safe }}</script>
  <style>{{ css }}</style>
</head>
<body>
  <div class="wrap">
    <nav class="breadcrumbs"><a href="{{ site_url }}">Glosix</a> / <a href="{{ blog_url }}">Блог</a>{% if category_name %} / <a href="{{ category_url }}">{{ category_name }}</a>{% endif %}</nav>
    <header>
      {% if category_name %}<span class="muted">{{ category_name }}</span>{% endif %}
      <h1>{{ title }}</h1>
      <p class="muted">{{ date_str }}{% if author_name %} · {{ author_name }}{% endif %}{% if reading_time_min %} · {{ reading_time_min }} мин{% endif %}</p>
    </header>
    {% if cover_url %}<img class="cover" src="{{ cover_url }}" alt="" />{% endif %}
    <article class="prose">{{ content_html | safe }}</article>
    {% if comments_enabled %}
    <section class="comments" id="blog-comments" data-slug="{{ slug }}">
      <h2>Комментарии</h2>
      <div id="comments-list"></div>
      <form class="comment-form" id="comment-form">
        <input name="author_name" placeholder="Ваше имя" required maxlength="120" />
        <textarea name="body" rows="4" placeholder="Комментарий" required maxlength="4000"></textarea>
        <button type="submit" class="btn btn-primary">Отправить</button>
        <p class="muted" id="comment-msg"></p>
      </form>
    </section>
    <script>
    (function(){
      const slug = {{ slug_json | safe }};
      const list = document.getElementById('comments-list');
      const form = document.getElementById('comment-form');
      const msg = document.getElementById('comment-msg');
      function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
      async function load(){
        try{
          const r = await fetch('/api/blog/posts/'+encodeURIComponent(slug)+'/comments');
          if(!r.ok) return;
          const items = await r.json();
          list.innerHTML = items.length ? items.map(c=>'<div class="comment"><strong>'+esc(c.author_name)+'</strong><span class="muted"> · '+new Date(c.created_at).toLocaleString('ru-RU')+'</span><p>'+esc(c.body)+'</p></div>').join('') : '<p class="muted">Пока нет комментариев.</p>';
        }catch(e){}
      }
      form.addEventListener('submit', async (e)=>{
        e.preventDefault();
        msg.textContent = '';
        const fd = new FormData(form);
        try{
          const r = await fetch('/api/blog/posts/'+encodeURIComponent(slug)+'/comments', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({author_name: fd.get('author_name'), body: fd.get('body')})
          });
          if(!r.ok){ const err = await r.json().catch(()=>({})); msg.textContent = err.detail || 'Ошибка'; return; }
          form.reset(); msg.textContent = 'Комментарий добавлен'; load();
        }catch(err){ msg.textContent = 'Ошибка отправки'; }
      });
      load();
    })();
    </script>
    {% endif %}
    <section class="blog-try-search">
      <h2>Попробуйте Glosix прямо сейчас</h2>
      <p class="blog-try-search-lead">Умный поиск с источниками и готовым ответом. Введите вопрос — откроется чат. Без регистрации можно искать как гость.</p>
      <form class="blog-try-search-form" action="/thread" method="get">
        <input type="search" name="q" placeholder="Например: как настроить VPN на роутере" required maxlength="2000" autocomplete="off" />
        <button type="submit">Искать</button>
      </form>
    </section>
    <footer class="footer">
      <a class="btn btn-secondary" href="{{ blog_url }}">← Все статьи</a>
      <a class="btn btn-primary" href="{{ site_url }}">На главную</a>
    </footer>
  </div>
</body>
</html>"""

_INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="{{ locale }}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Блог Glosix — статьи об ИИ-поиске и ассистентах</title>
  <meta name="description" content="Статьи Glosix: умный поиск, ИИ-ассистент, MAX-бот и полезные гайды." />
  <link rel="canonical" href="{{ blog_url }}" />
  <meta property="og:title" content="Блог Glosix — статьи об ИИ-поиске и ассистентах" />
  <meta property="og:description" content="Статьи Glosix: умный поиск, ИИ-ассистент, MAX-бот и полезные гайды." />
  <meta property="og:url" content="{{ blog_url }}" />
  <meta property="og:type" content="website" />
  <meta name="twitter:card" content="summary" />
  <meta name="twitter:title" content="Блог Glosix — статьи об ИИ-поиске и ассистентах" />
  <meta name="twitter:description" content="Статьи Glosix: умный поиск, ИИ-ассистент, MAX-бот и полезные гайды." />
  <style>{{ css }}</style>
</head>
<body>
  <div class="wrap wrap--wide">
    <h1>Блог Glosix</h1>
    <p class="lead">Статьи об умном поиске, ИИ-ассистенте и автоматизации в MAX</p>
    {% if categories %}
    <nav class="cat-chips">{% for c in categories %}<a class="cat-chip" href="{{ site_url }}/blog/category/{{ c.slug }}">{{ c.name }}</a>{% endfor %}</nav>
    {% endif %}
    <div class="grid">
      {% for p in posts %}
      <article class="card">
        <a href="{{ site_url }}/blog/{{ p.slug }}">
          {% if p.cover_url %}<img src="{{ p.cover_url }}" alt="" loading="lazy" />{% else %}<div style="aspect-ratio:16/9;background:#eef3f4"></div>{% endif %}
          <div class="card-body">
            {% if p.category_name %}<span class="muted">{{ p.category_name }}</span>{% endif %}
            <h2>{{ p.title }}</h2>
            {% if p.excerpt %}<p class="muted">{{ p.excerpt }}</p>{% endif %}
          </div>
        </a>
      </article>
      {% endfor %}
    </div>
    {% if not posts %}<p class="muted">Скоро здесь появятся статьи.</p>{% endif %}
  </div>
</body>
</html>"""

_CATEGORY_TEMPLATE = """<!DOCTYPE html>
<html lang="{{ locale }}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ category_name }} — Блог Glosix</title>
  {% if category_description %}<meta name="description" content="{{ category_description }}" />{% else %}<meta name="description" content="Статьи в категории «{{ category_name }}» — блог Glosix об умном поиске и ИИ-ассистенте." />{% endif %}
  <link rel="canonical" href="{{ canonical_url }}" />
  <meta property="og:title" content="{{ category_name }} — Блог Glosix" />
  {% if category_description %}<meta property="og:description" content="{{ category_description }}" />{% endif %}
  <meta property="og:url" content="{{ canonical_url }}" />
  <meta property="og:type" content="website" />
  <meta name="twitter:card" content="summary" />
  <meta name="twitter:title" content="{{ category_name }} — Блог Glosix" />
  {% if category_description %}<meta name="twitter:description" content="{{ category_description }}" />{% endif %}
  <style>{{ css }}</style>
</head>
<body>
  <div class="wrap wrap--wide">
    <nav class="breadcrumbs"><a href="{{ blog_url }}">Блог</a> / {{ category_name }}</nav>
    <h1>{{ category_name }}</h1>
    {% if category_description %}<p class="lead">{{ category_description }}</p>{% endif %}
    <div class="grid">
      {% for p in posts %}
      <article class="card"><a href="{{ site_url }}/blog/{{ p.slug }}"><div class="card-body"><h2>{{ p.title }}</h2>{% if p.excerpt %}<p class="muted">{{ p.excerpt }}</p>{% endif %}</div></a></article>
      {% endfor %}
    </div>
  </div>
</body>
</html>"""


def _env() -> Environment:
    return Environment(loader=BaseLoader(), autoescape=select_autoescape(["html", "xml"]))


def prerender_root() -> Path:
    settings = get_settings()
    root = Path(settings.upload_storage_dir) / "blog_prerender"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _locale_dir(locale: str = DEFAULT_LOCALE) -> Path:
    path = prerender_root() / locale
    path.mkdir(parents=True, exist_ok=True)
    (path / "posts").mkdir(exist_ok=True)
    (path / "categories").mkdir(exist_ok=True)
    return path


def _write(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def read_prerender(relative: str) -> str | None:
    path = prerender_root() / relative
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return None


def _format_date(dt: datetime | None) -> str:
    if not dt:
        return ""
    try:
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return ""


def _abs_media(site: str, media: dict | None) -> str:
    if not media or not media.get("url"):
        return ""
    url = media["url"]
    return url if url.startswith("http") else f"{site.rstrip('/')}{url}"


async def render_post_html(db: AsyncSession, post, *, comments: list | None = None) -> str:
    settings = get_settings()
    site = settings.public_web_url.rstrip("/")
    public = post_to_public(post)
    if comments is None and post.comments_enabled:
        comments = await list_approved_comments(db, post.id)
    category = post.category
    json_ld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": post.title,
            "description": public["meta_description"],
            "datePublished": post.published_at.isoformat() if post.published_at else None,
            "dateModified": post.updated_at.isoformat() if post.updated_at else None,
            "author": {"@type": "Person", "name": post.author_name or "Glosix"},
            "mainEntityOfPage": f"{site}{public['canonical_path']}",
            "image": _abs_media(site, public.get("og_image")),
        },
        ensure_ascii=False,
    )
    tpl = _env().from_string(_POST_TEMPLATE)
    return tpl.render(
        locale=post.locale or DEFAULT_LOCALE,
        meta_title=public["meta_title"],
        meta_description=public["meta_description"],
        meta_keywords=public["meta_keywords"],
        og_title=public["og_title"],
        og_description=public["og_description"],
        og_image=_abs_media(site, public.get("og_image")),
        canonical_url=f"{site}{public['canonical_path']}",
        robots_index=public["robots_index"],
        json_ld=json_ld,
        css=_BLOG_CSS,
        site_url=site,
        blog_url=f"{site}/blog",
        category_name=category.name if category else "",
        category_url=f"{site}/blog/category/{category.slug}" if category else "",
        title=post.title,
        date_str=_format_date(post.published_at),
        author_name=post.author_name or "",
        reading_time_min=post.reading_time_min,
        cover_url=_abs_media(site, media_out(post.cover_image)),
        content_html=post.content_html,
        comments_enabled=post.comments_enabled,
        slug=post.slug,
        slug_json=json.dumps(post.slug),
    )


async def render_index_html(db: AsyncSession) -> str:
    settings = get_settings()
    site = settings.public_web_url.rstrip("/")
    posts, _ = await list_posts_public(db, limit=50)
    categories = await list_categories(db)
    cards = []
    for p in posts:
        cards.append(
            {
                "slug": p.slug,
                "title": p.title,
                "excerpt": p.excerpt[:200],
                "cover_url": _abs_media(site, media_out(p.cover_image)),
                "category_name": p.category.name if p.category else "",
            }
        )
    tpl = _env().from_string(_INDEX_TEMPLATE)
    return tpl.render(
        locale=DEFAULT_LOCALE,
        css=_BLOG_CSS,
        site_url=site,
        blog_url=f"{site}/blog",
        categories=[{"slug": c.slug, "name": c.name} for c in categories],
        posts=cards,
    )


async def render_category_html(db: AsyncSession, category) -> str:
    settings = get_settings()
    site = settings.public_web_url.rstrip("/")
    posts, _ = await list_posts_public(db, category_slug=category.slug, limit=50)
    tpl = _env().from_string(_CATEGORY_TEMPLATE)
    return tpl.render(
        locale=DEFAULT_LOCALE,
        css=_BLOG_CSS,
        site_url=site,
        blog_url=f"{site}/blog",
        canonical_url=f"{site}/blog/category/{category.slug}",
        category_name=category.name,
        category_description=category.description or "",
        posts=[{"slug": p.slug, "title": p.title, "excerpt": p.excerpt[:160]} for p in posts],
    )


async def save_post_prerender(db: AsyncSession, post) -> None:
    if post.status != "published" or post.locale != DEFAULT_LOCALE:
        path = _locale_dir(post.locale or DEFAULT_LOCALE) / "posts" / f"{post.slug}.html"
        if path.exists():
            path.unlink(missing_ok=True)
        return
    html = await render_post_html(db, post)
    _write(_locale_dir() / "posts" / f"{post.slug}.html", html)


async def refresh_blog_prerender_for_post(db: AsyncSession, post) -> None:
    """Update prerender cache after publish/edit/delete."""
    await save_post_prerender(db, post)
    index_html = await render_index_html(db)
    _write(_locale_dir() / "index.html", index_html)
    for cat in await list_categories(db):
        html = await render_category_html(db, cat)
        _write(_locale_dir() / "categories" / f"{cat.slug}.html", html)


async def rebuild_all_prerender(db: AsyncSession) -> int:
    count = 0
    index_html = await render_index_html(db)
    _write(_locale_dir() / "index.html", index_html)
    count += 1
    categories = await list_categories(db)
    for cat in categories:
        html = await render_category_html(db, cat)
        _write(_locale_dir() / "categories" / f"{cat.slug}.html", html)
        count += 1
    posts, _ = await list_posts_public(db, limit=500)
    for post in posts:
        full = await get_post_by_slug(db, post.slug, locale=post.locale)
        if full:
            await save_post_prerender(db, full)
            count += 1
    logger.info("blog prerender rebuilt: %s files", count)
    return count
