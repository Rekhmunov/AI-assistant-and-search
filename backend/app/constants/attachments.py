"""Limits for search attachments (documents and images)."""

from app.models.user import Plan

MAX_ATTACHMENTS_PER_SEARCH = 10
MAX_EXTRACT_CHARS_PER_FILE = 32_000
MAX_TOTAL_ATTACHMENT_CHARS = 96_000

# Срок жизни вложений в uploaded_files (текст документов + бинарники фото на диске).
# Настраивается в админке (upload_ttl_hours); это значение по умолчанию.
UPLOAD_TTL_HOURS = 24

MAX_UPLOAD_BYTES_FREE = 8 * 1024 * 1024
MAX_UPLOAD_BYTES_PRO = 15 * 1024 * 1024


def max_upload_bytes(plan: Plan) -> int:
    return MAX_UPLOAD_BYTES_PRO if plan == Plan.PRO else MAX_UPLOAD_BYTES_FREE


def max_upload_mb(plan: Plan) -> int:
    return max_upload_bytes(plan) // 1024 // 1024
