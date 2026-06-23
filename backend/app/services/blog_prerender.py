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
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:#1a2328;background:#f5f7f8;line-height:1.6}
a{color:#20808d;text-decoration:none}a:hover{text-decoration:underline}
.layout{display:flex;min-height:100vh}
/* Сайдбар */
.sidebar{width:240px;flex-shrink:0;background:#fff;border-right:1px solid #e8edf0;position:sticky;top:0;height:100vh;overflow-y:auto}
.sidebar-hd{padding:20px 16px 12px;border-bottom:1px solid #e8edf0;font-size:1rem;font-weight:700;letter-spacing:-.01em}
.sidebar-nav{padding:8px}
.nav-item{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:8px;text-decoration:none;color:#5c6b73;font-size:.9rem;transition:background .12s,color .12s}
.nav-item:hover{background:#f4f7f8;color:#1a2328;text-decoration:none}
.nav-item.active{background:rgba(32,128,141,.08);color:#20808d;font-weight:500}
/* Контент */
.main{flex:1;min-width:0;max-width:760px;padding:28px 24px 56px;overflow-x:hidden}
/* Хлебные крошки */
.bc{font-size:.85rem;margin-bottom:12px;color:#5c6b73}
.bc a{color:#20808d}
/* Заголовок страницы */
.page-title{margin:0 0 6px;font-size:1.5rem;font-weight:700;letter-spacing:-.02em;color:#1a2328}
.page-lead{margin:0 0 20px;color:#5c6b73;font-size:.95rem}
/* Список статей */
.posts{display:flex;flex-direction:column}
.post-row{border-bottom:1px solid #e8edf0}
.post-row:first-child{border-top:1px solid #e8edf0}
.post-link{display:flex;gap:16px;padding:16px 0;text-decoration:none;color:inherit}
.post-link:hover .post-title{color:#20808d}
.post-thumb{flex-shrink:0;width:96px;height:64px;border-radius:8px;overflow:hidden;background:#fff;border:1px solid #e8edf0}
.post-thumb img{width:100%;height:100%;object-fit:cover;display:block}
.post-thumb-ph{width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:1.4rem;font-weight:700;color:#20808d;background:rgba(32,128,141,.07)}
.post-body{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}
.post-cat{font-size:.72rem;color:#20808d;text-transform:uppercase;letter-spacing:.05em;font-weight:600}
.post-title{margin:0;font-size:1rem;font-weight:600;line-height:1.35;color:#1a2328;transition:color .12s;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.post-excerpt{font-size:.85rem;color:#5c6b73;line-height:1.45;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden}
.post-meta{display:flex;align-items:center;gap:6px;font-size:.78rem;color:#5c6b73;margin-top:auto}
.sep{opacity:.4}
/* Статья */
.art-cat{display:inline-block;margin-bottom:8px;font-size:.72rem;color:#20808d;text-transform:uppercase;letter-spacing:.05em;font-weight:600}
.art-title{margin:0 0 12px;font-size:clamp(1.5rem,4vw,2rem);line-height:1.25;font-weight:700;letter-spacing:-.02em;color:#1a2328}
.art-meta{display:flex;flex-wrap:wrap;align-items:center;gap:6px;font-size:.85rem;color:#5c6b73;margin-bottom:24px}
.cover{width:100%;border-radius:12px;margin-bottom:28px;aspect-ratio:16/9;object-fit:cover;display:block;box-shadow:0 2px 12px rgba(0,0,0,.08)}
.prose{line-height:1.7;font-size:1.02rem;word-break:break-word;color:#1a2328}
.prose h2{margin:1.8em 0 .6em;font-size:1.35rem;font-weight:700;border-bottom:1px solid #e8edf0;padding-bottom:8px}
.prose h3{margin:1.4em 0 .5em;font-size:1.15rem;font-weight:600}
.prose p{margin:0 0 1.1em}
.prose img{max-width:100%!important;width:auto;height:auto!important;border-radius:10px;margin:1.2em 0;display:block;box-sizing:border-box;box-shadow:0 2px 12px rgba(0,0,0,.08)}
.prose a{color:#20808d;text-decoration:underline;text-decoration-thickness:1px;text-underline-offset:3px}
.prose ul,.prose ol{margin:0 0 1.1em;padding-left:1.5em}
.prose li{margin-bottom:.4em}
.prose blockquote{margin:1.2em 0;padding:12px 16px;border-left:3px solid #20808d;background:#f4f7f8;border-radius:0 8px 8px 0;color:#5c6b73;font-style:italic}
.prose code{background:#f0f4f5;padding:2px 6px;border-radius:4px;font-size:.9em;font-family:ui-monospace,monospace}
/* Кнопки */
.btn{display:inline-block;padding:10px 18px;border-radius:8px;font-weight:600;cursor:pointer;font:inherit;border:none}
.btn-primary{background:#20808d;color:#fff}.btn-primary:hover{background:#1a6b76;color:#fff;text-decoration:none}
.btn-secondary{border:1px solid #d8e0e3;color:#1a2328;background:#fff}.btn-secondary:hover{background:#f4f7f8;text-decoration:none}
/* Подвал статьи */
.art-footer{margin-top:40px;padding-top:24px;border-top:1px solid #e8edf0;display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.art-back{color:#5c6b73;font-size:.9rem;transition:color .12s}.art-back:hover{color:#20808d;text-decoration:none}
/* CTA */
.cta{margin-top:40px;padding:24px 20px;border-radius:12px;border:1px solid #d8e0e3;background:linear-gradient(180deg,#f7fafb 0%,#fff 100%)}
.cta h2{margin:0 0 8px;font-size:1.2rem;font-weight:600}
.cta-lead{margin:0 0 16px;color:#5c6b73;font-size:.95rem}
.cta-form{display:flex;flex-wrap:wrap;gap:10px}
.cta-form input{flex:1 1 220px;min-width:0;padding:12px 14px;border:1px solid #d8e0e3;border-radius:10px;font:inherit}
.cta-form input:focus{outline:none;border-color:#20808d;box-shadow:0 0 0 3px rgba(32,128,141,.12)}
.cta-form button{padding:12px 20px;border-radius:10px;background:#20808d;color:#fff;font:inherit;font-weight:600;cursor:pointer;border:none}
.cta-form button:hover{background:#1a6b76}
/* Комментарии */
.comments{margin-top:40px;padding-top:24px;border-top:1px solid #e8edf0}
.comment{padding:12px 0;border-bottom:1px solid #e8edf0}
.comment strong{display:block;margin-bottom:4px}
.comment-form{display:flex;flex-direction:column;gap:8px;margin-top:16px}
.comment-form input,.comment-form textarea{padding:10px;border:1px solid #d8e0e3;border-radius:8px;font:inherit}
/* Мобильная */
@media(max-width:768px){
  .layout{flex-direction:column}
  .sidebar{width:100%;height:auto;position:static;border-right:none;border-bottom:1px solid #e8edf0}
  .sidebar-nav{flex-direction:row;flex-wrap:nowrap;overflow-x:auto;display:flex;gap:6px;padding:4px 12px 12px;scrollbar-width:none}
  .sidebar-nav::-webkit-scrollbar{display:none}
  .nav-item{flex-shrink:0;padding:6px 12px;border-radius:999px;border:1px solid #d8e0e3;white-space:nowrap;font-size:.85rem}
  .nav-item.active{border-color:#20808d}
  .main{padding:16px 16px 80px;max-width:100%}
  .post-thumb{width:72px;height:52px}
  .post-excerpt{display:none}
  .art-footer{flex-direction:column;align-items:flex-start}
}
"""

_POST_TEMPLATE = """<!DOCTYPE html>
<html lang="{{ locale }}">
<head>
  <meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
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
<div class="layout">
  <aside class="sidebar">
    <div class="sidebar-hd"><a href="{{ blog_url }}" style="color:inherit;text-decoration:none">Блог Glosix</a></div>
    <nav class="sidebar-nav">
      <a class="nav-item" href="{{ blog_url }}">📋 Все статьи</a>
      {% for c in categories %}<a class="nav-item{{ ' active' if category_slug == c.slug else '' }}" href="{{ site_url }}/blog/category/{{ c.slug }}">📁 {{ c.name }}</a>{% endfor %}
    </nav>
  </aside>
  <main class="main">
    <div class="bc"><a href="{{ blog_url }}">Блог</a>{% if category_name %} / <a href="{{ category_url }}">{{ category_name }}</a>{% endif %}</div>
    <header>
      {% if category_name %}<a class="art-cat" href="{{ category_url }}">{{ category_name }}</a>{% endif %}
      <h1 class="art-title">{{ title }}</h1>
      <div class="art-meta">
        <span>{{ date_str }}</span>
        {% if author_name %}<span class="sep">·</span><span>{{ author_name }}</span>{% endif %}
        {% if reading_time_min %}<span class="sep">·</span><span>{{ reading_time_min }} мин чтения</span>{% endif %}
      </div>
    </header>
    {% if cover_url %}<img class="cover" src="{{ cover_url }}" alt="" loading="lazy" />{% endif %}
    <div class="prose">{{ content_html | safe }}</div>
    {% if comments_enabled %}
    <section class="comments" id="blog-comments">
      <h2>Комментарии</h2>
      <div id="comments-list"></div>
      <form class="comment-form" id="comment-form">
        <input name="author_name" placeholder="Ваше имя" required maxlength="120" />
        <textarea name="body" rows="4" placeholder="Комментарий" required maxlength="4000"></textarea>
        <button type="submit" class="btn btn-primary">Отправить</button>
        <p style="color:#5c6b73;font-size:.9rem" id="comment-msg"></p>
      </form>
    </section>
    <script>
    (function(){
      const slug = {{ slug_json | safe }};
      const list = document.getElementById('comments-list');
      const form = document.getElementById('comment-form');
      const msg = document.getElementById('comment-msg');
      function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
      async function load(){try{const r=await fetch('/api/blog/posts/'+encodeURIComponent(slug)+'/comments');if(!r.ok)return;const items=await r.json();list.innerHTML=items.length?items.map(c=>'<div class="comment"><strong>'+esc(c.author_name)+'</strong><span style="color:#5c6b73;font-size:.85rem"> · '+new Date(c.created_at).toLocaleString('ru-RU')+'</span><p>'+esc(c.body)+'</p></div>').join(''):'<p style="color:#5c6b73">Пока нет комментариев.</p>';}catch(e){}}
      form.addEventListener('submit',async(e)=>{e.preventDefault();msg.textContent='';const fd=new FormData(form);try{const r=await fetch('/api/blog/posts/'+encodeURIComponent(slug)+'/comments',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({author_name:fd.get('author_name'),body:fd.get('body')})});if(!r.ok){const err=await r.json().catch(()=>({}));msg.textContent=err.detail||'Ошибка';return;}form.reset();msg.textContent='Комментарий добавлен';load();}catch(err){msg.textContent='Ошибка отправки';}});
      load();
    })();
    </script>
    {% endif %}
    <section class="cta">
      <h2>Попробуйте Glosix прямо сейчас</h2>
      <p class="cta-lead">Умный поиск с источниками и готовым ответом. Без регистрации можно искать как гость.</p>
      <form class="cta-form" action="/thread" method="get">
        <input type="search" name="q" placeholder="Например: как настроить VPN на роутере" required maxlength="2000" autocomplete="off" />
        <button type="submit">Искать</button>
      </form>
    </section>
    <footer class="art-footer">
      <a class="art-back" href="{{ blog_url }}">← Все статьи</a>
      <a class="btn btn-primary" href="{{ site_url }}">Попробовать Glosix</a>
    </footer>
  </main>
</div>
</body>
</html>"""

_SIDEBAR_HTML = """<aside class="sidebar">
  <div class="sidebar-hd"><a href="{{ blog_url }}" style="color:inherit;text-decoration:none">Блог Glosix</a></div>
  <nav class="sidebar-nav">
    <a class="nav-item{{ ' active' if active_slug == '' else '' }}" href="{{ blog_url }}">📋 Все статьи</a>
    {% for c in categories %}<a class="nav-item{{ ' active' if active_slug == c.slug else '' }}" href="{{ site_url }}/blog/category/{{ c.slug }}">📁 {{ c.name }}</a>{% endfor %}
  </nav>
</aside>"""

_POSTS_LIST_HTML = """{% for p in posts %}
<div class="post-row"><a class="post-link" href="{{ site_url }}/blog/{{ p.slug }}">
  <div class="post-thumb">{% if p.cover_url %}<img src="{{ p.cover_url }}" alt="" loading="lazy" />{% else %}<div class="post-thumb-ph">{{ p.title[0] }}</div>{% endif %}</div>
  <div class="post-body">
    {% if p.category_name %}<span class="post-cat">{{ p.category_name }}</span>{% endif %}
    <h2 class="post-title">{{ p.title }}</h2>
    {% if p.excerpt %}<p class="post-excerpt">{{ p.excerpt }}</p>{% endif %}
    <div class="post-meta">{{ p.date_str }}{% if p.reading_time_min %}<span class="sep">·</span>{{ p.reading_time_min }} мин{% endif %}</div>
  </div>
</a></div>
{% endfor %}
{% if not posts %}<p style="color:#5c6b73;padding:40px 0">Скоро здесь появятся статьи.</p>{% endif %}"""

_INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Блог Glosix — статьи об ИИ-поиске и ассистентах</title>
  <meta name="description" content="Статьи Glosix: умный поиск, ИИ-ассистент, MAX-бот и полезные гайды." />
  <link rel="canonical" href="{{ blog_url }}" />
  <meta property="og:title" content="Блог Glosix — статьи об ИИ-поиске и ассистентах" />
  <meta property="og:description" content="Статьи Glosix: умный поиск, ИИ-ассистент, MAX-бот и полезные гайды." />
  <meta property="og:url" content="{{ blog_url }}" /><meta property="og:type" content="website" />
  <style>{{ css }}</style>
</head>
<body>
<div class="layout">
  """ + _SIDEBAR_HTML + """
  <main class="main">
    <h1 class="page-title">Все статьи</h1>
    <p class="page-lead">Статьи об умном поиске, ИИ-ассистенте и автоматизации в MAX</p>
    <div class="posts">""" + _POSTS_LIST_HTML + """</div>
  </main>
</div>
</body></html>"""

_CATEGORY_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{ category_name }} — Блог Glosix</title>
  {% if category_description %}<meta name="description" content="{{ category_description }}" />{% else %}<meta name="description" content="Статьи в категории «{{ category_name }}» — блог Glosix." />{% endif %}
  <link rel="canonical" href="{{ canonical_url }}" />
  <meta property="og:title" content="{{ category_name }} — Блог Glosix" />
  <meta property="og:url" content="{{ canonical_url }}" /><meta property="og:type" content="website" />
  <style>{{ css }}</style>
</head>
<body>
<div class="layout">
  """ + _SIDEBAR_HTML + """
  <main class="main">
    <div class="bc"><a href="{{ blog_url }}">Блог</a> / {{ category_name }}</div>
    <h1 class="page-title">{{ category_name }}</h1>
    {% if category_description %}<p class="page-lead">{{ category_description }}</p>{% endif %}
    <div class="posts">""" + _POSTS_LIST_HTML + """</div>
  </main>
</div>
</body></html>"""


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
    all_categories = await list_categories(db)
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
        categories=[{"slug": c.slug, "name": c.name} for c in all_categories],
        category_name=category.name if category else "",
        category_slug=category.slug if category else "",
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
                "date_str": _format_date(p.published_at),
                "reading_time_min": p.reading_time_min,
            }
        )
    tpl = _env().from_string(_INDEX_TEMPLATE)
    return tpl.render(
        locale=DEFAULT_LOCALE,
        css=_BLOG_CSS,
        site_url=site,
        blog_url=f"{site}/blog",
        categories=[{"slug": c.slug, "name": c.name} for c in categories],
        active_slug="",
        posts=cards,
    )


async def render_category_html(db: AsyncSession, category) -> str:
    settings = get_settings()
    site = settings.public_web_url.rstrip("/")
    posts, _ = await list_posts_public(db, category_slug=category.slug, limit=50)
    all_categories = await list_categories(db)
    tpl = _env().from_string(_CATEGORY_TEMPLATE)
    return tpl.render(
        locale=DEFAULT_LOCALE,
        css=_BLOG_CSS,
        site_url=site,
        blog_url=f"{site}/blog",
        canonical_url=f"{site}/blog/category/{category.slug}",
        categories=[{"slug": c.slug, "name": c.name} for c in all_categories],
        active_slug=category.slug,
        category_name=category.name,
        category_description=category.description or "",
        posts=[{
            "slug": p.slug,
            "title": p.title,
            "excerpt": p.excerpt[:160],
            "cover_url": _abs_media(site, media_out(p.cover_image)),
            "category_name": p.category.name if p.category else "",
            "date_str": _format_date(p.published_at),
            "reading_time_min": p.reading_time_min,
        } for p in posts],
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
