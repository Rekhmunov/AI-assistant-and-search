from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class BlogMediaOut(BaseModel):
    id: UUID
    url: str
    width: int | None = None
    height: int | None = None
    alt_text: str = ""
    size_bytes: int = 0

    model_config = {"from_attributes": True}


class BlogCategoryOut(BaseModel):
    id: UUID
    slug: str
    name: str
    description: str = ""

    model_config = {"from_attributes": True}


class BlogCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=120)
    description: str = ""


class BlogCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    slug: str | None = Field(default=None, max_length=120)
    description: str | None = None
    sort_order: int | None = None


class BlogPostListItem(BaseModel):
    id: UUID
    slug: str
    title: str
    excerpt: str
    published_at: datetime | None
    reading_time_min: int
    view_count: int = 0
    category: BlogCategoryOut | None = None
    cover_image: BlogMediaOut | None = None

    model_config = {"from_attributes": True}


class BlogCommentOut(BaseModel):
    id: UUID
    author_name: str
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BlogCommentCreate(BaseModel):
    author_name: str = Field(min_length=2, max_length=120)
    body: str = Field(min_length=2, max_length=4000)


class BlogPostPublic(BaseModel):
    id: UUID
    slug: str
    title: str
    excerpt: str
    content_html: str
    published_at: datetime | None
    updated_at: datetime
    reading_time_min: int
    author_name: str = ""
    comments_enabled: bool = False
    locale: str = "ru"
    category: BlogCategoryOut | None = None
    cover_image: BlogMediaOut | None = None
    meta_title: str
    meta_description: str
    meta_keywords: str
    og_title: str
    og_description: str
    og_image: BlogMediaOut | None = None
    canonical_path: str
    robots_index: bool


class BlogPostAdminOut(BlogPostListItem):
    status: str
    content_html: str
    category_id: UUID | None = None
    cover_image_id: UUID | None = None
    og_image_id: UUID | None = None
    meta_title: str = ""
    meta_description: str = ""
    meta_keywords: str = ""
    og_title: str = ""
    og_description: str = ""
    robots_index: bool = True
    created_at: datetime
    updated_at: datetime
    author_email: str | None = None
    author_name: str = ""
    comments_enabled: bool = False
    locale: str = "ru"
    view_count: int = 0


class BlogPostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    slug: str | None = Field(default=None, max_length=200)
    excerpt: str = ""
    content_html: str = "<p></p>"
    status: str = "draft"
    category_id: UUID | None = None
    cover_image_id: UUID | None = None
    og_image_id: UUID | None = None
    meta_title: str = ""
    meta_description: str = ""
    meta_keywords: str = ""
    og_title: str = ""
    og_description: str = ""
    robots_index: bool = True
    published_at: datetime | None = None
    author_name: str = ""
    comments_enabled: bool = False
    locale: str = "ru"


class BlogPostUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    slug: str | None = Field(default=None, max_length=200)
    excerpt: str | None = None
    content_html: str | None = None
    status: str | None = None
    category_id: UUID | None = None
    cover_image_id: UUID | None = None
    og_image_id: UUID | None = None
    meta_title: str | None = None
    meta_description: str | None = None
    meta_keywords: str | None = None
    og_title: str | None = None
    og_description: str | None = None
    robots_index: bool | None = None
    published_at: datetime | None = None
    author_name: str | None = None
    comments_enabled: bool | None = None
    locale: str | None = None
    view_count: int | None = None


class BlogMediaUploadOut(BaseModel):
    id: UUID
    url: str
    width: int | None
    height: int | None
    alt_text: str
    size_bytes: int


class BlogGenerateArticleIn(BaseModel):
    topic: str = Field(min_length=3, max_length=500)
    requirements: str = ""
    category_name: str | None = None
    fill_seo: bool = True
    generate_slug: bool = True


class BlogGenerateArticleOut(BaseModel):
    title: str
    slug: str
    excerpt: str
    content_html: str
    meta_title: str
    meta_description: str
    meta_keywords: str
    og_title: str
    og_description: str


class BlogGenerateCoverIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=800)
    alt_text: str = ""


class BlogGenerateCoverOut(BaseModel):
    media: BlogMediaUploadOut


class BlogGenerateMetaIn(BaseModel):
    field: str = Field(description="meta_title | meta_description | meta_keywords | og_title | og_description")
    title: str = Field(min_length=1, max_length=500)
    excerpt: str = ""
    content_html: str = ""


class BlogGenerateMetaOut(BaseModel):
    field: str
    value: str
    max_length: int
    min_length: int
    length: int
    hint: str
