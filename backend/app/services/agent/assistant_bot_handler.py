"""Обработчик личных сообщений для агента «Личный ассистент».

Пайплайн: голос/фото → текст → SearchFlow → ответ в бот.
Прогресс: редактирование сообщения «Думаю...» → «Ищу...» → «Пишу ответ...» → финал.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentInstance, AgentStatus
from app.models.thread import Thread, ThreadType
from app.models.user import Plan, User
from app.services.agent.session_thread import (
    clear_session,
    get_or_create_session_thread,
    touch_session,
)
from app.services.bot import MaxBotService

logger = logging.getLogger(__name__)

_MAX_TEXT_LEN = 3800  # MAX лимит 4000, оставляем запас на кнопку/ссылку

# Набор команд ассистента
_ASSISTANT_CMDS = frozenset({"new", "history"})


def _parse_cmd(low: str) -> str | None:
    """Извлекает имя команды из текста вида '/new', 'new', '/new arg'. None если не команда."""
    raw = low.strip()
    if raw.startswith("/"):
        raw = raw[1:]
    word = raw.split()[0] if raw.split() else ""
    return word if word in _ASSISTANT_CMDS else None

_STATUS_ROUTING = "⏳ Обрабатываем запрос…"
_STATUS_SEARCH  = "🔍 Ищем в интернете…"
_STATUS_ANSWER  = "✍️ Формируем ответ…"


async def _find_active_assistant(
    db: AsyncSession, *, max_user_id: int
) -> tuple[AgentInstance, "User"] | None:
    """
    Ищет активного ассистента через пользователя.
    Возвращает (agent, user) или None.
    Надёжнее чем поиск по AgentInstance.max_user_id (может быть 0 при создании).
    """
    user_result = await db.execute(
        select(User).where(User.max_user_id == max_user_id).limit(1)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        return None

    result = await db.execute(
        select(AgentInstance).where(
            AgentInstance.user_id == user.id,
            AgentInstance.status == AgentStatus.ACTIVE.value,
        )
    )
    for agent in result.scalars().all():
        if str((agent.config or {}).get("template") or "") == "assistant":
            return agent, user
    return None



def _thread_url(thread_id: uuid.UUID, settings) -> str:
    """URL треда: мини-апп если MAX_BOT_URL задан, иначе веб-сайт."""
    bot_base = (settings.max_bot_url or "").strip().rstrip("/").split("?")[0]
    if bot_base:
        return f"{bot_base}?startapp=thread_{thread_id}"
    web = (settings.public_web_url or "https://glosix.ru").rstrip("/")
    return f"{web}/thread/{thread_id}"


def _open_button(thread_id: uuid.UUID, settings) -> dict:
    """Кнопка «Открыть в Glosix» → link (open_app не работает в DM)."""
    return MaxBotService.make_keyboard_attachment([[{
        "type": "link",
        "text": "🔍 Открыть в Glosix",
        "url": _thread_url(thread_id, settings),
    }]])


_HEADER_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_CODE_BLOCK_RE = re.compile(r"```[^\n]*\n?", re.MULTILINE)
_CITATION_RE = re.compile(r"\[\d+\]")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|\s]+\|$")


def _convert_tables(text: str) -> str:
    """
    Конвертирует markdown-таблицы в читаемый формат для MAX-чата.
    | Параметр | A | B | → **Параметр:** A — val_a / B — val_b
    """
    lines = text.split("\n")
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        # Определяем таблицу: строка с | ... | и следующая строка — разделитель |---|
        if (
            stripped.startswith("|")
            and stripped.endswith("|")
            and i + 1 < len(lines)
            and _TABLE_SEP_RE.match(lines[i + 1].strip())
        ):
            headers = [h.strip() for h in stripped[1:-1].split("|")]
            i += 2  # пропускаем заголовок и разделитель
            while i < len(lines):
                row = lines[i].strip()
                if not (row.startswith("|") and row.endswith("|")):
                    break
                cells = [c.strip() for c in row[1:-1].split("|")]
                param = cells[0] if cells else ""
                if param and not re.match(r"^[-: ]+$", param):
                    if len(headers) >= 3 and len(cells) >= 3:
                        parts = [
                            f"{headers[j]} — {cells[j]}"
                            for j in range(1, min(len(headers), len(cells)))
                            if j < len(cells) and cells[j]
                        ]
                        result.append(f"**{param}:** " + " / ".join(parts))
                    elif len(cells) >= 2 and cells[1]:
                        result.append(f"**{param}:** {cells[1]}")
                i += 1
        else:
            result.append(line)
            i += 1
    return "\n".join(result)


def _deduplicate_paragraphs(text: str, *, max_repeats: int = 2) -> str:
    """
    Removes repeated paragraphs caused by LLM hallucination loops.
    Keeps each unique paragraph at most max_repeats times, then truncates.
    Also detects repeated sentence sequences (50+ chars) and cuts there.
    """
    # Split into paragraphs and remove duplicates beyond threshold
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    seen: dict[str, int] = {}
    result: list[str] = []
    truncated = False
    for para in paragraphs:
        key = para[:80].lower()  # fingerprint on first 80 chars
        count = seen.get(key, 0)
        if count >= max_repeats:
            truncated = True
            break
        seen[key] = count + 1
        result.append(para)

    cleaned = "\n\n".join(result)

    # Secondary check: detect repeated sentence chunks (≥50 chars appearing 3+ times)
    if not truncated:
        import re as _re
        # Find any sentence of 50+ chars that appears 3+ times
        sentences = _re.findall(r".{50,}?[.!?]\s", cleaned)
        for sent in sentences:
            if cleaned.count(sent) >= 3:
                idx = cleaned.rfind(sent, 0, cleaned.index(sent, cleaned.index(sent) + 1))
                if idx > 0:
                    cleaned = cleaned[:idx].rstrip()
                break

    return cleaned


def _format_for_max_chat(text: str) -> str:
    """
    Адаптирует LLM-ответ для красивого отображения в MAX-чате.
    Применяется ТОЛЬКО к ответам бота-ассистента, не к веб-приложению.
    """
    text = _HEADER_RE.sub(r"**\1**", text)
    text = _CODE_BLOCK_RE.sub("", text)
    text = _CITATION_RE.sub("", text)
    text = _convert_tables(text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    # Remove LLM hallucination loops (repeated paragraphs/sentences)
    text = _deduplicate_paragraphs(text)
    return text.strip()


def _split_for_max(text: str, max_len: int = _MAX_TEXT_LEN) -> list[str]:
    """
    Разбивает текст на части по MAX-лимиту.
    Делит по абзацам → строкам → предложениям, чтобы не резать посередине.
    """
    if len(text) <= max_len:
        return [text]
    parts: list[str] = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        chunk = text[:max_len]
        # Ищем лучшее место для разрыва
        cut = -1
        for sep in ("\n\n", "\n", ". ", "! ", "? "):
            idx = chunk.rfind(sep)
            if idx > int(max_len * 0.6):
                cut = idx + len(sep)
                break
        if cut <= 0:
            cut = chunk.rfind(" ")
            if cut <= 0:
                cut = max_len
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return [p for p in parts if p]



async def _collect_search_result(
    db: AsyncSession,
    user: User,
    redis_client,
    query: str,
    thread_id: uuid.UUID,
    attachment_file_ids: list[uuid.UUID] | None = None,
    on_status=None,  # async callable(str) для обновления статуса в боте
    max_user_id: int | None = None,  # для отправки файлов в DM
) -> tuple[str, list[dict], list[str]]:
    """
    Запускает SearchFlowService и собирает ответ + изображения + follow-up вопросы.
    Возвращает (answer_text, images_list, follow_ups_list).
    on_status — async callback(text) для обновления статусного сообщения в боте.
    """
    from app.services.search_flow import SearchFlowService
    from app.core.limiter import RateLimiter
    from app.core.config import get_settings

    settings = get_settings()
    limiter = RateLimiter(redis_client, settings)

    answer_parts: list[str] = []
    images: list[dict] = []
    follow_ups: list[str] = []
    error_msg: str | None = None
    _answer_started = False
    _doc_ready_events: list[dict] = []  # document_ready events to send as files

    async def _update_status(text: str) -> None:
        if on_status:
            try:
                await on_status(text)
            except Exception:
                pass

    flow = SearchFlowService()
    try:
        async for raw_event in flow.stream_search(
            db,
            user,
            limiter,
            query,
            thread_id,
            attachment_ids=attachment_file_ids or [],
            redis_client=redis_client,
            client_ip=None,
        ):
            event_type, data = _parse_sse(raw_event)
            if event_type == "route":
                # Обновляем статус в зависимости от того, нужен ли поиск
                if data.get("needs_search"):
                    await _update_status(_STATUS_SEARCH)
                else:
                    await _update_status(_STATUS_ANSWER)
            elif event_type == "token":
                text = data.get("text") or ""
                if text:
                    if not _answer_started:
                        _answer_started = True
                        await _update_status(_STATUS_ANSWER)
                    answer_parts.append(text)
            elif event_type == "reset_answer":
                # search_flow сбрасывает ответ (markdown wrap / template evasion)
                # — очищаем буфер чтобы не задваивать текст
                answer_parts.clear()
            elif event_type == "images":
                imgs = data.get("images")
                if isinstance(imgs, list):
                    images.extend(imgs)
            elif event_type == "follow_ups":
                qs = data.get("questions")
                if isinstance(qs, list):
                    follow_ups = [str(q) for q in qs if q][:3]
            elif event_type == "document_ready":
                # PDF/image tools send files via this event — collect for sending to MAX
                if data.get("file_id") and data.get("filename"):
                    _doc_ready_events.append(data)
            elif event_type == "error":
                code = data.get("code", "")
                if code in ("rate_limit", "free_rate_limit", "guest_rate_limit"):
                    error_msg = (
                        "❌ Дневной лимит запросов исчерпан. "
                        "Попробуйте завтра или проверьте тариф в Glosix."
                    )
                elif code == "free_image_gen_pro":
                    error_msg = "❌ Генерация картинок доступна только в тарифе Pro."
                elif code == "vision_unavailable":
                    error_msg = (
                        "Сейчас распознавание фотографий временно недоступно — мы уже разбираемся. "
                        "Попробуйте повторить через несколько минут."
                    )
                elif code in ("image_gen_failed", "image_gen_unavailable", "image_gen_rate_limit"):
                    if code == "image_gen_rate_limit":
                        error_msg = "❌ Достигнут дневной лимит генерации изображений. Попробуйте завтра."
                    elif code == "image_gen_unavailable":
                        error_msg = "❌ Генерация изображений временно недоступна. Попробуйте позже."
                    else:
                        error_msg = "❌ Не удалось сгенерировать изображение. Попробуйте ещё раз."
                else:
                    error_msg = data.get("message") or "❌ Не удалось обработать запрос."
                break
    except Exception as exc:
        logger.exception("assistant_bot: search flow error: %s", exc)
        error_msg = "❌ Произошла ошибка при обработке запроса. Попробуйте ещё раз."

    if error_msg:
        return error_msg, [], []

    answer = "".join(answer_parts).strip()
    if not answer:
        answer = "Не удалось получить ответ. Попробуйте переформулировать вопрос."
    else:
        # Remove LLM looping artifacts before storing in thread and sending to DM
        answer = _deduplicate_paragraphs(answer)

    # Send files to DM if document_ready events were collected
    if _doc_ready_events:
        from app.services.upload_storage import load_upload_bytes
        from app.services.agent.file_delivery import upload_bytes_to_max
        from app.core.config import get_settings as _get_settings
        from sqlalchemy import select as _select
        from app.models.uploaded_file import UploadedFile as _UF
        _settings = _get_settings()
        for doc in _doc_ready_events:
            try:
                fid_str = doc.get("file_id", "")
                filename = doc.get("filename", "file")
                if not fid_str:
                    continue
                import uuid as _uuid
                fid = _uuid.UUID(fid_str)
                _uf_res = await db.execute(_select(_UF).where(_UF.id == fid))
                _uf = _uf_res.scalar_one_or_none()
                if not _uf or not _uf.storage_key:
                    continue
                file_bytes = load_upload_bytes(_uf.storage_key)
                if not file_bytes:
                    continue
                _token, attachments = await upload_bytes_to_max(file_bytes, filename)
                if attachments:
                    from app.services.bot import MaxBotService as _Bot
                    _bot = _Bot()
                    await _bot.send_message(max_user_id, "", attachments=attachments)
            except Exception as _fe:
                logger.warning("DM file send failed for %s: %s", doc.get("filename"), _fe)

    return answer, images, follow_ups


def _parse_sse(raw: str) -> tuple[str, dict]:
    """Парсит строку SSE в (event_type, data_dict)."""
    event_type = ""
    data_str = ""
    for line in raw.strip().split("\n"):
        if line.startswith("event: "):
            event_type = line[7:].strip()
        elif line.startswith("data: "):
            data_str = line[6:].strip()
    try:
        data = json.loads(data_str) if data_str else {}
    except json.JSONDecodeError:
        data = {}
    return event_type, data


async def _upload_images_to_max(
    bot: MaxBotService,
    images: list[dict],
    settings,
    db=None,
) -> list[dict]:
    """
    Загружает сгенерированные изображения из хранилища в MAX и возвращает
    список attachment-объектов для включения в send_message.
    Изображения защищены Bearer-токеном — читаем байты напрямую из хранилища.
    """
    import asyncio
    import re
    from app.services.upload_storage import load_upload_bytes

    _FILE_ID_RE = re.compile(
        r"/files/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/",
        re.I,
    )
    result_attachments: list[dict] = []

    for img in images[:3]:
        url = (img.get("url") or "").strip()
        if not url:
            continue
        try:
            m = _FILE_ID_RE.search(url)
            image_bytes: bytes | None = None
            if m and db is not None:
                from sqlalchemy import select as _select
                from app.models.uploaded_file import UploadedFile
                import uuid as _uuid
                db_result = await db.execute(
                    _select(UploadedFile).where(
                        UploadedFile.id == _uuid.UUID(m.group(1))
                    )
                )
                row = db_result.scalar_one_or_none()
                if row and row.storage_key:
                    image_bytes = load_upload_bytes(row.storage_key)
                    logger.info("assistant_bot: loaded image from storage len=%d", len(image_bytes) if image_bytes else 0)

            if not image_bytes:
                import httpx
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(url)
                if resp.status_code == 200:
                    image_bytes = resp.content
                    logger.info("assistant_bot: loaded image via http len=%d", len(image_bytes))
                else:
                    logger.warning("assistant_bot: http image fetch failed status=%d url=%s", resp.status_code, url[:80])

            if not image_bytes:
                logger.warning("assistant_bot: no image bytes for url=%s", url[:80])
                continue

            await asyncio.sleep(0.5)
            token = await bot.upload_media(image_bytes, "image.jpg", "image")
            logger.info("assistant_bot: upload_media token=%s", token[:20] if token else None)
            if token:
                await asyncio.sleep(1.0)
                result_attachments.append({"type": "image", "payload": {"token": token}})
            else:
                logger.warning("assistant_bot: upload_media returned no token for url=%s", url[:80])
        except Exception as exc:
            logger.warning("assistant_bot: image upload failed: %s", exc)

    return result_attachments


async def _cmd_new(
    db: AsyncSession,
    redis_client,
    *,
    max_user_id: int,
    agent: AgentInstance,
    user: User,
    bot: MaxBotService,
) -> None:
    """Команда /new — сбросить сессию, начать новый тред."""
    await clear_session(redis_client, user_id=user.id, agent_id=agent.id)
    # Создаём новый тред заранее, чтобы показать его в ответе
    thread = await get_or_create_session_thread(
        db, redis_client, user=user, agent_id=agent.id
    )
    await db.commit()
    from app.core.config import get_settings
    settings = get_settings()
    await bot.send_message(
        max_user_id,
        "🆕 Начат новый диалог. Задавайте вопрос!",
        attachments=[_open_button(thread.id, settings)],
    )


async def _cmd_history(
    db: AsyncSession,
    *,
    max_user_id: int,
    user: User,
    bot: MaxBotService,
) -> None:
    """Команда /history — последние 5 тредов в виде кнопок."""
    from sqlalchemy import nulls_last
    from app.core.config import get_settings
    settings = get_settings()

    # Последние 5 тредов (не закреплённых, не agent-треды)
    result = await db.execute(
        select(Thread)
        .where(
            Thread.user_id == user.id,
            Thread.deleted_at.is_(None),
            Thread.thread_type == ThreadType.SEARCH,
            Thread.pinned_at.is_(None),
        )
        .order_by(Thread.last_message_at.desc())
        .limit(5)
    )
    threads = result.scalars().all()

    if not threads:
        await bot.send_message(max_user_id, "История пуста. Начните новый диалог!")
        return

    bot_base = (settings.max_bot_url or "").strip().rstrip("/").split("?")[0]
    web_base = (settings.public_web_url or "https://glosix.ru").rstrip("/")

    def _thread_btn_url(tid) -> str:
        return f"{bot_base}?startapp=thread_{tid}" if bot_base else f"{web_base}/thread/{tid}"

    def _history_url() -> str:
        return f"{bot_base}?startapp=history" if bot_base else f"{web_base}/history"

    buttons = []
    for t in threads:
        title = (t.title or "Диалог")[:38]
        ts = t.last_message_at
        label = f"{title} · {ts.strftime('%d.%m %H:%M')}" if ts else title
        # callback: переключает сессию в боте без открытия приложения
        buttons.append([{
            "type": "callback",
            "text": label,
            "payload": f"assistant_thread:{t.id}",
        }])

    # «Вся история» → открывает приложение
    buttons.append([{"type": "link", "text": "📚 Вся история", "url": _history_url()}])

    keyboard = MaxBotService.make_keyboard_attachment(buttons)
    await bot.send_message(
        max_user_id,
        "Последние диалоги:",
        attachments=[keyboard],
    )


async def _cmd_status(
    *,
    max_user_id: int,
    user: User,
    redis_client,
    bot: MaxBotService,
) -> None:
    """Команда /status — остаток запросов."""
    from app.core.limiter import RateLimiter
    from app.core.config import get_settings
    settings = get_settings()
    limiter = RateLimiter(redis_client, settings)
    used, limit = await limiter.usage_and_limit(user)
    plan_label = "Pro" if user.plan == Plan.PRO else "Free"
    remaining = max(0, limit - used)
    text = (
        f"📊 Статус аккаунта:\n"
        f"Тариф: {plan_label}\n"
        f"Использовано сегодня: {used} / {limit}\n"
        f"Осталось: {remaining} запросов"
    )
    await bot.send_message(max_user_id, text)


async def handle_assistant_dm(
    db: AsyncSession,
    redis_client,
    *,
    max_user_id: int,
    text: str,
    payload: dict[str, Any],
    message_id_value: str | None = None,
    bot: MaxBotService | None = None,
) -> bool:
    """
    Основная точка входа для DM-сообщений к «Личному ассистенту».
    Возвращает True если сообщение обработано.
    """
    bot = bot or MaxBotService()

    found = await _find_active_assistant(db, max_user_id=max_user_id)
    if not found:
        return False
    agent, user = found

    from app.core.config import get_settings
    settings = get_settings()

    # ── Голосовое сообщение ──
    effective_text = text
    from app.services.agent.max_media import transcribe_voice_message
    if not effective_text and payload:
        voice_text = await transcribe_voice_message(payload)
        if voice_text:
            effective_text = voice_text
            logger.info("assistant_bot: voice transcribed len=%s", len(voice_text))

    low = (effective_text or "").strip().lower()

    # ── Slash-команды ──
    cmd = _parse_cmd(low)

    if cmd == "new":
        await _cmd_new(db, redis_client, max_user_id=max_user_id, agent=agent, user=user, bot=bot)
        await db.commit()
        return True

    if cmd == "history":
        await _cmd_history(db, max_user_id=max_user_id, user=user, bot=bot)
        return True


    # ── Файловые вложения из MAX DM (PDF, docx и т.д.) ──────────────────────
    # В MAX файл и текст — два разных сообщения. Сохраняем file_id в Redis
    # чтобы следующее текстовое сообщение могло его использовать.
    _PENDING_FILE_KEY = f"dm_pending_file:{max_user_id}"
    _PENDING_FILE_TTL = 300  # 5 минут

    from app.services.agent.max_media import message_has_files, extract_file_attachments

    _dm_file_ids: list = []
    if message_has_files(payload):
        file_atts = extract_file_attachments(payload)
        for fa in file_atts[:2]:
            try:
                from app.services.upload_storage import save_upload_bytes
                from app.models.uploaded_file import UploadedFile as _UF
                from app.services.file_parser import extract_text
                from datetime import datetime, timezone as _tz, timedelta
                import uuid as _uuid
                _file_bytes = await bot.download_url(fa["url"])
                if not _file_bytes:
                    continue
                _fname = fa["filename"]
                _ext = _fname.rsplit(".", 1)[-1].lower() if "." in _fname else "bin"
                _mime = "application/pdf" if _ext == "pdf" else f"application/{_ext}"
                _fid = _uuid.uuid4()
                _key = save_upload_bytes(user.id, _fid, _file_bytes, _ext)
                try:
                    _extracted = extract_text(_fname, _file_bytes)
                except Exception:
                    _extracted = ""
                _ufo = _UF(
                    id=_fid, user_id=user.id, filename=_fname,
                    mime_type=_mime, size_bytes=len(_file_bytes),
                    media_kind="document", storage_key=_key,
                    extracted_text=_extracted,
                    expires_at=datetime.now(_tz.utc) + timedelta(hours=24),
                )
                db.add(_ufo)
                await db.flush()
                _dm_file_ids.append(str(_fid))
                logger.info("assistant_bot: DM file saved fid=%s name=%s", _fid, _fname)
            except Exception as _fe:
                logger.warning("assistant_bot: DM file save failed: %s", _fe)
        if _dm_file_ids:
            import json as _json
            await redis_client.setex(_PENDING_FILE_KEY, _PENDING_FILE_TTL, _json.dumps(_dm_file_ids))

    # Подтягиваем файл из Redis если он был прислан предыдущим сообщением
    _pending_raw = await redis_client.get(_PENDING_FILE_KEY)
    _pending_file_ids: list = []
    if _pending_raw and effective_text:
        try:
            import json as _json
            import uuid as _uuid2
            _pending_file_ids = [_uuid2.UUID(x) for x in _json.loads(_pending_raw)]
            await redis_client.delete(_PENDING_FILE_KEY)
            logger.info("assistant_bot: using %d pending DM file(s)", len(_pending_file_ids))
        except Exception:
            pass

    if not effective_text and not _has_images(payload) and not _dm_file_ids:
        return False

    # ── Немедленный отбойник — сохраняем message_id для редактирования ──
    sent_status = await bot.send_message(max_user_id, _STATUS_ROUTING)
    status_mid = sent_status.message_id if sent_status.ok else None

    try:
        query = (effective_text or "").strip()

        # ── Фото из MAX: скачиваем и сохраняем в Glosix UploadedFile ──────────
        # Это позволяет: 1) показать превью в треде мини-аппа,
        #               2) прогнать Vision через стандартный pipeline.
        _attachment_file_ids: list = []
        if _has_images(payload):
            from app.services.agent.max_media import load_message_vision_images
            from app.services.upload_storage import save_upload_bytes
            from app.models.uploaded_file import UploadedFile
            from datetime import timedelta
            import uuid as _uuid

            try:
                vision_images = await load_message_vision_images(payload, bot=bot)
                for vi in vision_images[:3]:
                    try:
                        import base64
                        img_bytes = base64.b64decode(vi.data_base64)
                        # Определяем формат из реальных байт (не из заголовка MAX)
                        from app.services.file_format import sniff_ext_from_bytes as _sniff
                        import base64 as _b64
                        try:
                            _raw = _b64.b64decode(vi.data_base64)
                            _sniffed = _sniff(_raw)
                        except Exception:
                            _sniffed = None
                        if _sniffed in ("jpg", "png", "webp"):
                            ext = _sniffed
                        elif "png" in (vi.media_type or ""):
                            ext = "png"
                        elif "webp" in (vi.media_type or ""):
                            ext = "webp"
                        else:
                            ext = "jpg"
                        vi_mime = "image/jpeg" if ext == "jpg" else f"image/{ext}"
                        logger.debug(
                            "VISION_DEBUG save UploadedFile ext=%s vi_mime=%s vi.media_type=%s",
                            ext, vi_mime, vi.media_type,
                        )
                        file_id = _uuid.uuid4()
                        storage_key = save_upload_bytes(user.id, file_id, img_bytes, ext)
                        from datetime import datetime, timezone as _tz
                        uf = UploadedFile(
                            id=file_id,
                            user_id=user.id,
                            filename=f"photo.{ext}",
                            mime_type=vi_mime,
                            size_bytes=len(img_bytes),
                            media_kind="image",
                            storage_key=storage_key,
                            extracted_text="",
                            expires_at=datetime.now(_tz.utc) + timedelta(hours=24),
                        )
                        db.add(uf)
                        await db.flush()
                        _attachment_file_ids.append(file_id)
                    except Exception as img_exc:
                        logger.warning("assistant_bot: image save failed: %s", img_exc)
            except Exception as vis_exc:
                logger.warning("assistant_bot: image load failed: %s", vis_exc)

        # Объединяем вложения: из текущего сообщения + из Redis (файл из предыдущего сообщения)
        _all_attachment_ids = list(_attachment_file_ids) + list(_pending_file_ids)

        if not query and not _all_attachment_ids:
            await bot.send_message(max_user_id, "Пожалуйста, добавьте текст к сообщению.")
            return True

        # ── Добавляем ограничение длины для бот-контекста ──
        llm_query = (query or "Что на фото?") + "\n\n[Ответ не длиннее 3500 знаков включая пробелы и знаки препинания. Если ответ короче — оставь как есть.]"

        # ── Сессионный тред ──
        thread = await get_or_create_session_thread(
            db, redis_client, user=user, agent_id=agent.id
        )

        # Обновляем заголовок если тред новый (placeholder)
        if thread.title in ("Новый диалог", "", None):
            words = query.split() if query else ["Фото"]
            thread.title = " ".join(words[:8])[:120] or "Фото"
            await db.flush()

        # ── Запуск поиска с обновлением статусов ──
        async def _on_status(text: str) -> None:
            if status_mid:
                await bot.edit_message(status_mid, text)

        try:
            answer, images, follow_ups = await _collect_search_result(
                db, user, redis_client, llm_query, thread.id,
                on_status=_on_status,
                attachment_file_ids=_all_attachment_ids if _all_attachment_ids else None,
                max_user_id=max_user_id,
            )
        except Exception as search_exc:
            logger.warning("assistant_bot: search with attachment failed, retrying without: %s", search_exc)
            # Повтор без вложений если vision/attachment упал
            answer, images, follow_ups = await _collect_search_result(
                db, user, redis_client, llm_query, thread.id,
                on_status=_on_status,
                max_user_id=max_user_id,
            )

        # ── Обновляем TTL сессии в Redis ──
        await touch_session(
            redis_client, user_id=user.id, agent_id=agent.id, thread_id=thread.id
        )

        # ── Форматируем и разбиваем на части (без обрезки) ──
        answer_formatted = _format_for_max_chat(answer)
        parts = _split_for_max(answer_formatted)

        # ── Клавиатура: до 2 follow-up кнопок + «Открыть» (только в последней части) ──
        open_row = [{"type": "link", "text": "🔍 Открыть в Glosix",
                     "url": _thread_url(thread.id, settings)}]
        rows = [[{"type": "message", "text": q, "payload": q}] for q in follow_ups[:2]]
        rows.append(open_row)
        keyboard = MaxBotService.make_keyboard_attachment(rows)

        # ── Загружаем изображения в MAX ДО отправки ответа ──
        image_attachments: list[dict] = []
        if images:
            image_attachments = await _upload_images_to_max(bot, images, settings, db=db)

        # ── Отправляем ответ ──
        # Правило: ✅ не показываем. Статусное сообщение всегда становится первой
        # (или единственной) частью ответа через edit_message.
        # Исключение — картинки: edit_message их не поддерживает, там статус меняется
        # на ✅ (это технически неизбежно).
        last_attachments = image_attachments + [keyboard]

        if image_attachments:
            # edit_message не поддерживает вложения — удаляем статусное сообщение,
            # чтобы оно не оставалось висеть отдельной галочкой.
            if status_mid:
                try:
                    await bot.delete_message(status_mid)
                except Exception:
                    pass
            for part in parts[:-1]:
                await bot.send_message(max_user_id, part)
            await bot.send_message(max_user_id, parts[-1], attachments=last_attachments)

        elif len(parts) == 1:
            # Одна часть: статус становится ответом
            if status_mid:
                edited = await bot.edit_message(status_mid, parts[0], attachments=[keyboard])
                if not edited:
                    await bot.send_message(max_user_id, parts[0], attachments=[keyboard])
            else:
                await bot.send_message(max_user_id, parts[0], attachments=[keyboard])

        else:
            # Несколько частей: статус становится первой частью (без клавиатуры)
            if status_mid:
                edited = await bot.edit_message(status_mid, parts[0])
                if not edited:
                    await bot.send_message(max_user_id, parts[0])
            else:
                await bot.send_message(max_user_id, parts[0])
            # Средние части
            for part in parts[1:-1]:
                await bot.send_message(max_user_id, part)
            # Последняя часть с клавиатурой
            await bot.send_message(max_user_id, parts[-1], attachments=[keyboard])

    except Exception as exc:
        logger.exception("assistant_bot: handle error: %s", exc)
        await bot.send_message(max_user_id, "❌ Произошла ошибка. Попробуйте ещё раз.")

    return True


def _has_images(payload: dict[str, Any]) -> bool:
    from app.services.agent.max_media import message_has_images
    return message_has_images(payload)


async def _handle_vision(
    payload: dict[str, Any],
    text: str,
    bot: MaxBotService,
    max_user_id: int,
) -> str | None:
    """Загружает фото из MAX и получает описание через vision."""
    from app.services.agent.max_media import load_message_vision_images
    from app.services.vision_service import summarize_vision_for_search

    images = await load_message_vision_images(payload, bot=bot)
    if not images:
        return None

    query = text or "Опиши что на изображении."
    try:
        result = await summarize_vision_for_search(images, query)
        return result
    except Exception as exc:
        logger.warning("assistant_bot: vision failed: %s", exc)
        return None
