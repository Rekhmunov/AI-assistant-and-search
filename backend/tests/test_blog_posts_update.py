"""Blog post update edge cases."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

from app.models.blog import BlogPost
from app.services.blog_posts import update_post


def test_update_post_ignores_empty_slug():
    post = BlogPost(
        id=uuid.uuid4(),
        slug="existing-slug",
        title="Title",
        content_html="<p>x</p>",
        status="draft",
    )
    db = AsyncMock()
    db.flush = AsyncMock()

    asyncio.run(update_post(db, post, {"slug": ""}))

    assert post.slug == "existing-slug"
    db.add.assert_not_called()
