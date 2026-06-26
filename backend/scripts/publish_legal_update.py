#!/usr/bin/env python3
"""
Публикует обновлённую версию юридического документа из HTML-файла в базу данных.

Запуск на сервере:
  docker compose -f docker-compose.prod.yml exec backend \
    python scripts/publish_legal_update.py pd_consent

Аргументы:
  slug      — идентификатор документа (pd_consent, privacy, offer, ...)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "app" / "data" / "legal"


async def main() -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else "pd_consent"

    # Ищем HTML-файл по имени: pd_consent_ru.html, privacy_ru.html, etc.
    candidates = list(DATA_DIR.glob(f"{slug}_*.html")) + list(DATA_DIR.glob(f"{slug}.html"))
    if not candidates:
        print(f"[ERROR] HTML-файл для slug='{slug}' не найден в {DATA_DIR}")
        sys.exit(1)

    html_file = candidates[0]
    content_html = html_file.read_text(encoding="utf-8")
    print(f"[OK] Загружен файл: {html_file.name} ({len(content_html)} байт)")

    from app.core.config import get_settings
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy import select, func
    from app.models.legal_document import LegalDocument, LegalDocumentVersion
    from app.services.legal_html import sanitize_legal_html

    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        result = await db.execute(select(LegalDocument).where(LegalDocument.slug == slug))
        doc = result.scalar_one_or_none()
        if not doc:
            print(f"[ERROR] Документ slug='{slug}' не найден в БД. Сначала запустите ensure_default_documents.")
            await engine.dispose()
            sys.exit(1)

        # Определяем следующий номер версии
        max_ver_res = await db.execute(
            select(func.coalesce(func.max(LegalDocumentVersion.version_number), 0))
            .where(LegalDocumentVersion.document_id == doc.id)
        )
        next_version = int(max_ver_res.scalar_one() or 0) + 1

        clean_html = sanitize_legal_html(content_html)
        version = LegalDocumentVersion(
            document_id=doc.id,
            version_number=next_version,
            content_html=clean_html,
        )
        db.add(version)
        await db.flush()

        doc.current_version_id = version.id
        await db.commit()

        print(f"[OK] Опубликована версия {next_version} документа '{doc.title}' (slug={slug})")
        print(f"     Version ID: {version.id}")
        print(f"     URL: https://glosix.ru{doc.public_path}")
        print()
        print("[INFO] Пользователи с устаревшим согласием получат запрос на повторное принятие.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
