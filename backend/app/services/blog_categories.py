"""Blog categories service — re-exports from blog_posts for backward compatibility."""

from app.services.blog_posts import list_categories, get_category_by_slug

__all__ = ["list_categories", "get_category_by_slug"]
