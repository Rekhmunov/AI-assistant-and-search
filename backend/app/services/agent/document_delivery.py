"""Генерация и отправка документов (docx, pdf, xlsx) и изображений в MAX."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.agent.file_delivery import upload_bytes_to_max
from app.services.agent.image_delivery import build_image_attachments
from app.services.bot import MaxBotService
from app.services.doc_gen_llm import generate_document_structure
from app.services.doc_gen_routing import wants_document_generation
from app.services.docx_builder import build_docx_bytes
from app.services.pdf_builder import build_pdf_bytes
from app.services.providers.factory import resolve_runtime_providers
from app.services.xlsx_builder import build_xlsx_bytes

logger = logging.getLogger(__name__)

VALID_OUTPUT_FORMATS = frozenset({"docx", "pdf", "xlsx"})

_FORMAT_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bxlsx\b|\bexcel\b|эксел|таблиц", re.I), "xlsx"),
    (re.compile(r"\bpdf\b|пдф", re.I), "pdf"),
    (re.compile(r"\bdocx?\b|\bword\b|ворд|документ\s+word", re.I), "docx"),
]

_FILE_SEND_RE = re.compile(
    r"(?:отправ|пришли|скинь|выложи|пошли|загрузи|приложи|дай\s+файл|"
    r"сформируй\s+и\s+отправ|сделай\s+и\s+отправ)",
    re.I,
)

_IMAGE_SEND_RE = re.compile(
    r"(?:отправ|пришли|скинь|сгенерир|нарисуй|сделай).{0,40}"
    r"(?:картин|изображ|фото|иллюстрац|картинк)",
    re.I,
)


@dataclass
class FileDeliveryResult:
    text: str
    attachments: list[dict]
    keyboard: dict | None = None  # inline_keyboard attachment для MAX


def infer_output_format(text: str, explicit: str | None = None) -> str | None:
    fmt = (explicit or "").strip().lower()
    if fmt in VALID_OUTPUT_FORMATS:
        return fmt
    for pattern, name in _FORMAT_ALIASES:
        if pattern.search(text or ""):
            return name
    return None


def wants_document_delivery(text: str) -> bool:
    clean = (text or "").strip()
    if not clean:
        return False
    if wants_document_generation(clean):
        return True
    if _FILE_SEND_RE.search(clean) and infer_output_format(clean):
        return True
    if _FILE_SEND_RE.search(clean) and re.search(
        r"документ|файл|отчет|отчёт|таблиц", clean, re.I
    ):
        return True
    return False


def wants_image_delivery(text: str) -> bool:
    clean = (text or "").strip()
    if not clean:
        return False
    return bool(_IMAGE_SEND_RE.search(clean))


def _filename_for_format(fmt: str, title: str) -> str:
    safe = re.sub(r"[^\w\s-]", "", (title or "document")[:40]).strip() or "document"
    safe = re.sub(r"\s+", "_", safe)
    ext = {"docx": "docx", "pdf": "pdf", "xlsx": "xlsx"}.get(fmt, "docx")
    return f"{safe}.{ext}"


async def _build_document_bytes(
    db: AsyncSession,
    redis_client,
    user: User,
    instruction: str,
    output_format: str,
) -> tuple[bytes, str, str]:
    llm, _, answer_model, _, _ = await resolve_runtime_providers(db, redis_client, user=user)
    structure = await generate_document_structure(
        llm,
        instruction.strip(),
        answer_model=answer_model,
    )
    fmt = output_format if output_format in VALID_OUTPUT_FORMATS else "docx"
    if fmt == "pdf":
        data = build_pdf_bytes(structure, show_glosix_footer=True)
    elif fmt == "xlsx":
        data = build_xlsx_bytes(structure)
    else:
        data = build_docx_bytes(structure, show_glosix_footer=True)
    filename = _filename_for_format(fmt, structure.title)
    caption = (structure.title or "Документ").strip()[:500]
    return data, filename, caption


async def build_document_delivery_content(
    db: AsyncSession,
    redis_client,
    user: User,
    instruction: str,
    *,
    output_format: str | None = None,
    bot: MaxBotService | None = None,
) -> FileDeliveryResult:
    fmt = infer_output_format(instruction, output_format) or "docx"
    try:
        data, filename, caption = await _build_document_bytes(
            db, redis_client, user, instruction, fmt
        )
    except Exception as exc:
        logger.warning("Agent document generation failed: %s", exc)
        return FileDeliveryResult(
            text=f"Не удалось сформировать документ: {exc}",
            attachments=[],
        )

    _token, attachments = await upload_bytes_to_max(data, filename, bot=bot)
    if not attachments:
        return FileDeliveryResult(
            text=f"{caption}\n\nДокумент сформирован, но не удалось загрузить в MAX.",
            attachments=[],
        )
    return FileDeliveryResult(text=caption, attachments=attachments)


async def build_image_delivery_content(
    instruction: str,
    *,
    bot: MaxBotService | None = None,
    db=None,
    user=None,
    redis_client=None,
) -> FileDeliveryResult:
    text, attachments, share_url = await build_image_attachments(
        instruction, bot=bot, db=db, user=user, redis_client=redis_client
    )

    keyboard: dict | None = None
    if share_url:
        keyboard = MaxBotService.make_keyboard_attachment(
            [[{"type": "link", "text": "📥 Скачать", "url": share_url}]]
        )

    return FileDeliveryResult(text=text, attachments=attachments or [], keyboard=keyboard)


async def try_build_file_reply(
    db: AsyncSession,
    redis_client,
    user: User,
    text: str,
    *,
    output_format: str | None = None,
    bot: MaxBotService | None = None,
) -> FileDeliveryResult | None:
    if wants_image_delivery(text) and not infer_output_format(text, output_format):
        prompt = text.strip()
        return await build_image_delivery_content(prompt, bot=bot)
    if wants_document_delivery(text):
        return await build_document_delivery_content(
            db,
            redis_client,
            user,
            text,
            output_format=output_format,
            bot=bot,
        )
    return None
