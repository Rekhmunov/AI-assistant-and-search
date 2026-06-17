import asyncio
import logging
import mimetypes
from dataclasses import dataclass

import httpx

from app.core.config import Settings, get_settings
from app.services.bot_message_format import prepare_max_message
from app.services.bot_rate_limit import throttle_max_api

logger = logging.getLogger(__name__)

# https://dev.max.ru/docs-api — platform-api.max.ru, Authorization header, 30 rps
BOT_API_BASE = "https://platform-api.max.ru"

# Пауза после upload перед send (attachment.not.ready — dev.max.ru/docs-api/methods/POST/uploads)
UPLOAD_TO_SEND_DELAY_SEC = 1.0
FILE_UPLOAD_TO_SEND_DELAY_SEC = 2.5


@dataclass
class BotSendResult:
    ok: bool
    error: str | None = None
    retry_after_sec: float | None = None
    message_id: str | None = None


class MaxBotService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def _auth_headers(self, *, json_body: bool = True) -> dict[str, str]:
        token = self.settings.bot_token.strip()
        headers = {"Authorization": token}
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    async def _request_with_rate_limit(self, call):
        await throttle_max_api()
        return await call()

    async def send_message(
        self,
        user_id: int | None,
        text: str,
        attachments: list[dict] | None = None,
        *,
        chat_id: int | None = None,
        text_format: str | None = None,
        notify: bool = True,
        max_attempts: int = 3,
    ) -> BotSendResult:
        if not self.settings.bot_token.strip():
            return BotSendResult(ok=False, error="bot_token not configured")
        if user_id is None and chat_id is None:
            return BotSendResult(ok=False, error="no max_user_id or chat_id")

        text, text_format = prepare_max_message(text, text_format)
        body: dict = {"text": text, "notify": notify}
        if text_format in {"markdown", "html"}:
            body["format"] = text_format
        if attachments:
            body["attachments"] = attachments

        params: dict[str, int] = {}
        if chat_id is not None:
            params["chat_id"] = int(chat_id)
        elif user_id is not None:
            params["user_id"] = int(user_id)

        for attempt in range(max_attempts):
            try:
                async def _post():
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        return await client.post(
                            f"{BOT_API_BASE}/messages",
                            params=params,
                            headers=self._auth_headers(),
                            json=body,
                        )

                response = await self._request_with_rate_limit(_post)
            except httpx.HTTPError as exc:
                logger.warning("MAX send_message network error user_id=%s: %s", user_id, exc)
                return BotSendResult(ok=False, error=str(exc))

            if response.is_success:
                message_id = None
                try:
                    payload = response.json()
                    logger.debug(
                        "MAX send_message OK user_id=%s chat_id=%s response=%s",
                        user_id, params.get("chat_id"), str(payload)[:300],
                    )
                    if isinstance(payload, dict):
                        message = payload.get("message")
                        if isinstance(message, dict):
                            mid = (
                                message.get("mid")
                                or message.get("message_id")
                                or message.get("id")
                            )
                            if mid is not None:
                                message_id = str(mid)
                        elif payload.get("message_id") is not None:
                            message_id = str(payload["message_id"])
                except ValueError:
                    pass
                return BotSendResult(ok=True, message_id=message_id)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 60.0
                except (TypeError, ValueError):
                    delay = 60.0
                if attempt + 1 < max_attempts:
                    await asyncio.sleep(min(delay, 120.0))
                    continue
                return BotSendResult(ok=False, error="rate_limited", retry_after_sec=delay)

            detail = response.text[:500]
            logger.warning(
                "MAX send_message failed user_id=%s chat_id=%s HTTP %s: %s",
                user_id,
                params.get("chat_id"),
                response.status_code,
                detail,
            )
            if "attachment.not.ready" in detail.lower() and attempt + 1 < max_attempts:
                await asyncio.sleep(2.0 * (attempt + 1))
                continue

            return BotSendResult(ok=False, error=detail or f"HTTP {response.status_code}")

        return BotSendResult(ok=False, error="send failed")

    @staticmethod
    def make_keyboard_attachment(rows: list[list[dict]]) -> dict:
        """Формирует вложение типа inline_keyboard для MAX API."""
        return {
            "type": "inline_keyboard",
            "payload": {"buttons": rows},
        }

    async def edit_message(
        self,
        message_id: str,
        text: str,
        *,
        remove_keyboard: bool = False,
    ) -> bool:
        """
        Редактирует сообщение бота (PUT /messages?message_id=...).
        remove_keyboard=True — убирает inline_keyboard передав attachments=[].
        Сообщения с inline_keyboard редактируются без ограничения по давности.
        """
        if not self.settings.bot_token.strip():
            return False
        mid = (message_id or "").strip()
        if not mid:
            return False

        body: dict = {"text": text}
        if remove_keyboard:
            body["attachments"] = []

        try:
            async def _put():
                async with httpx.AsyncClient(timeout=15.0) as client:
                    return await client.put(
                        f"{BOT_API_BASE}/messages",
                        params={"message_id": mid},
                        headers=self._auth_headers(),
                        json=body,
                    )

            response = await self._request_with_rate_limit(_put)
            if not response.is_success:
                logger.warning("edit_message failed mid=%s: HTTP %s %s", mid, response.status_code, response.text[:200])
            return response.is_success
        except Exception as exc:
            logger.warning("edit_message error mid=%s: %s", mid, exc)
            return False

    async def answer_callback(
        self,
        callback_id: str,
        notification: str = "",
    ) -> bool:
        """
        Отвечает на нажатие inline-кнопки (POST /answers).
        Обязателен после любого message_callback — иначе кнопка остаётся «нажатой».
        """
        if not self.settings.bot_token.strip():
            return False
        try:
            body: dict = {}
            if notification:
                body["notification"] = notification[:200]

            async def _post():
                async with httpx.AsyncClient(timeout=15.0) as client:
                    return await client.post(
                        f"{BOT_API_BASE}/answers",
                        params={"callback_id": callback_id},
                        headers=self._auth_headers(),
                        json=body,
                    )

            response = await self._request_with_rate_limit(_post)
            if not response.is_success:
                logger.warning("answer_callback failed: HTTP %s %s", response.status_code, response.text[:200])
            return response.is_success
        except Exception as exc:
            logger.warning("answer_callback error: %s", exc)
            return False

    async def delete_message(self, message_id: str, *, max_attempts: int = 2) -> BotSendResult:
        """
        Удаляет сообщение в MAX (DELETE /messages?message_id=…).
        Требует права администратора; по правилам платформы — обычно сообщения младше 24 ч.
        """
        if not self.settings.bot_token.strip():
            return BotSendResult(ok=False, error="bot_token not configured")
        mid = (message_id or "").strip()
        if not mid:
            return BotSendResult(ok=False, error="message_id required")

        for attempt in range(max_attempts):
            try:
                async def _delete():
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        return await client.delete(
                            f"{BOT_API_BASE}/messages",
                            params={"message_id": mid},
                            headers=self._auth_headers(json_body=False),
                        )

                response = await self._request_with_rate_limit(_delete)
            except httpx.HTTPError as exc:
                logger.warning("MAX delete_message network error mid=%s: %s", mid, exc)
                return BotSendResult(ok=False, error=str(exc))

            if response.is_success:
                return BotSendResult(ok=True)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 30.0
                except (TypeError, ValueError):
                    delay = 30.0
                if attempt + 1 < max_attempts:
                    await asyncio.sleep(min(delay, 120.0))
                    continue
                return BotSendResult(ok=False, error="rate_limited", retry_after_sec=delay)

            detail = response.text[:500]
            logger.warning(
                "MAX delete_message failed mid=%s HTTP %s: %s",
                mid,
                response.status_code,
                detail,
            )
            return BotSendResult(ok=False, error=detail or f"HTTP {response.status_code}")

        return BotSendResult(ok=False, error="delete failed")

    async def upload_media(self, data: bytes, filename: str, media_type: str) -> str | None:
        """Upload image, video, file or audio to MAX and return attachment token."""
        if not self.settings.bot_token.strip():
            return None
        if media_type not in {"image", "video", "file", "audio"}:
            return None

        headers = self._auth_headers(json_body=False)

        async def _init_upload():
            async with httpx.AsyncClient(timeout=120.0) as client:
                return await client.post(
                    f"{BOT_API_BASE}/uploads",
                    params={"type": media_type},
                    headers=headers,
                )

        upload_resp = await self._request_with_rate_limit(_init_upload)
        if not upload_resp.is_success:
            logger.warning("MAX upload init failed: %s", upload_resp.text[:300])
            return None

        body = upload_resp.json()
        upload_url = body.get("url")
        token = body.get("token")
        if not upload_url:
            return str(token) if token else None

        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        async def _upload_file():
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Multipart upload на CDN URL.
                # ВАЖНО: НЕ задаём Content-Type вручную — httpx сам добавит boundary.
                # Ручная установка заголовка без boundary ломает парсинг на сервере.
                return await client.post(
                    upload_url,
                    files={"data": (filename, data, content_type)},
                )

        put_resp = await _upload_file()
        if not put_resp.is_success:
            logger.warning("MAX upload POST failed: %s", put_resp.text[:300])
            return str(token) if token else None

        try:
            put_body = put_resp.json()
            if isinstance(put_body, dict) and put_body.get("token"):
                return str(put_body["token"])
        except ValueError:
            pass

        return str(token) if token else None

    async def get_group_messages(
        self,
        chat_id: int,
        *,
        from_timestamp: int | None = None,
        count: int = 50,
    ) -> list[dict]:
        """
        GET /messages?chat_id=...&from=...&count=...
        Читает историю сообщений группы для восстановления пропущенных записей.
        Требует что бот — администратор чата.
        """
        if not self.settings.bot_token.strip():
            return []
        params: dict = {"chat_id": int(chat_id), "count": min(count, 100)}
        if from_timestamp is not None:
            params["from"] = int(from_timestamp)

        async def _get():
            async with httpx.AsyncClient(timeout=30.0) as client:
                return await client.get(
                    f"{BOT_API_BASE}/messages",
                    params=params,
                    headers=self._auth_headers(json_body=False),
                )

        try:
            response = await self._request_with_rate_limit(_get)
        except httpx.HTTPError as exc:
            logger.warning("MAX get_group_messages network error chat_id=%s: %s", chat_id, exc)
            return []
        if not response.is_success:
            logger.warning(
                "MAX get_group_messages failed chat_id=%s HTTP %s: %s",
                chat_id, response.status_code, response.text[:300],
            )
            return []
        try:
            data = response.json()
        except ValueError:
            return []
        messages = data.get("messages") if isinstance(data, dict) else None
        return messages if isinstance(messages, list) else []

    async def get_messages_by_ids(self, message_ids: list[str]) -> list[dict]:
        if not self.settings.bot_token.strip() or not message_ids:
            return []
        ids_param = ",".join(str(mid).strip() for mid in message_ids if str(mid).strip())
        if not ids_param:
            return []

        async def _get():
            async with httpx.AsyncClient(timeout=30.0) as client:
                return await client.get(
                    f"{BOT_API_BASE}/messages",
                    params={"message_ids": ids_param},
                    headers=self._auth_headers(json_body=False),
                )

        try:
            response = await self._request_with_rate_limit(_get)
        except httpx.HTTPError as exc:
            logger.warning("MAX get_messages network error: %s", exc)
            return []
        if not response.is_success:
            logger.warning("MAX get_messages failed HTTP %s: %s", response.status_code, response.text[:300])
            return []
        try:
            data = response.json()
        except ValueError:
            return []
        messages = data.get("messages")
        return messages if isinstance(messages, list) else []

    async def download_url(self, url: str) -> bytes | None:
        if not url or not url.startswith("http"):
            return None
        token = self.settings.bot_token.strip()
        headers = {"Authorization": token} if token else {}

        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("MAX download_url failed %s: %s", url[:80], exc)
            return None
        if response.is_success:
            return response.content
        if token:
            try:
                async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                    response = await client.get(url)
                if response.is_success:
                    return response.content
            except httpx.HTTPError:
                pass
        logger.warning("MAX download_url HTTP %s for %s", response.status_code, url[:80])
        return None

    async def get_me(self) -> dict | None:
        if not self.settings.bot_token.strip():
            return None

        async def _get():
            async with httpx.AsyncClient(timeout=30.0) as client:
                return await client.get(
                    f"{BOT_API_BASE}/me",
                    headers=self._auth_headers(json_body=False),
                )

        try:
            response = await self._request_with_rate_limit(_get)
        except httpx.HTTPError as exc:
            logger.warning("MAX get_me network error: %s", exc)
            return None
        if not response.is_success:
            logger.warning("MAX get_me failed HTTP %s: %s", response.status_code, response.text[:300])
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    async def get_chat(self, chat_id: int) -> dict | None:
        if not self.settings.bot_token.strip():
            return None

        async def _get():
            async with httpx.AsyncClient(timeout=30.0) as client:
                return await client.get(
                    f"{BOT_API_BASE}/chats/{int(chat_id)}",
                    headers=self._auth_headers(json_body=False),
                )

        try:
            response = await self._request_with_rate_limit(_get)
        except httpx.HTTPError as exc:
            logger.warning("MAX get_chat network error chat_id=%s: %s", chat_id, exc)
            return None
        if not response.is_success:
            logger.warning(
                "MAX get_chat failed chat_id=%s HTTP %s: %s",
                chat_id,
                response.status_code,
                response.text[:300],
            )
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    async def get_chat_members(
        self,
        chat_id: int,
        *,
        user_ids: list[int] | None = None,
        count: int = 20,
    ) -> list[dict]:
        """
        GET /chats/{chatId}/members — бот должен быть админом чата, иначе API вернёт ошибку.
        """
        if not self.settings.bot_token.strip():
            return []
        params: dict[str, int | str] = {"count": max(1, min(100, count))}
        if user_ids:
            params["user_ids"] = ",".join(str(int(uid)) for uid in user_ids)

        async def _get():
            async with httpx.AsyncClient(timeout=30.0) as client:
                return await client.get(
                    f"{BOT_API_BASE}/chats/{int(chat_id)}/members",
                    params=params,
                    headers=self._auth_headers(json_body=False),
                )

        try:
            response = await self._request_with_rate_limit(_get)
        except httpx.HTTPError as exc:
            logger.warning("MAX get_chat_members network error chat_id=%s: %s", chat_id, exc)
            return []
        if not response.is_success:
            logger.warning(
                "MAX get_chat_members failed chat_id=%s HTTP %s: %s",
                chat_id,
                response.status_code,
                response.text[:300],
            )
            return []
        try:
            data = response.json()
        except ValueError:
            return []
        members = data.get("members") if isinstance(data, dict) else None
        return members if isinstance(members, list) else []

    async def check_bot_is_group_admin(self, chat_id: int) -> bool | None:
        """
        Проверяет, является ли бот администратором группы/канала.
        True/False — по данным API; None — не удалось проверить (нет токена, бот не в чате, нет прав на members).
        """
        me = await self.get_me()
        if not me:
            logger.warning("check_bot_is_group_admin: get_me() returned None, chat_id=%s", chat_id)
            return None
        bot_user_id = me.get("user_id")
        if bot_user_id is None:
            logger.warning("check_bot_is_group_admin: no user_id in /me response, chat_id=%s", chat_id)
            return None
        members = await self.get_chat_members(int(chat_id), user_ids=[int(bot_user_id)], count=1)
        logger.warning(
            "check_bot_is_group_admin: chat_id=%s bot_user_id=%s members_count=%s",
            chat_id, bot_user_id, len(members),
        )
        if not members:
            chat = await self.get_chat(int(chat_id))
            if isinstance(chat, dict):
                status = str(chat.get("status") or "").lower()
                if status in {"removed", "left", "closed"}:
                    return False
            return None
        member = members[0] if isinstance(members[0], dict) else {}
        is_admin = member.get("is_admin")
        is_owner = member.get("is_owner")
        logger.warning(
            "check_bot_is_group_admin: chat_id=%s is_admin=%s is_owner=%s",
            chat_id, is_admin, is_owner,
        )
        if is_admin is True or is_owner is True:
            return True
        if is_admin is False and is_owner is False:
            return False
        permissions = member.get("permissions")
        if isinstance(permissions, list) and permissions:
            return True
        return False

    async def get_chat_by_link(self, link: str) -> dict | None:
        """GET /chats/{link} — канал по публичной ссылке."""
        if not self.settings.bot_token.strip():
            return None
        slug = (link or "").strip().lstrip("@").strip("/")
        if not slug or len(slug) > 256:
            return None

        async def _get():
            async with httpx.AsyncClient(timeout=30.0) as client:
                return await client.get(
                    f"{BOT_API_BASE}/chats/{slug}",
                    headers=self._auth_headers(json_body=False),
                )

        try:
            response = await self._request_with_rate_limit(_get)
        except httpx.HTTPError as exc:
            logger.warning("MAX get_chat_by_link network error link=%s: %s", slug[:40], exc)
            return None
        if not response.is_success:
            logger.warning(
                "MAX get_chat_by_link failed link=%s HTTP %s: %s",
                slug[:40],
                response.status_code,
                response.text[:300],
            )
            return None
        try:
            data = response.json()
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    async def register_webhook(
        self,
        url: str,
        *,
        secret: str | None = None,
    ) -> bool:
        """
        Регистрирует или обновляет webhook (POST /subscriptions).
        Включает все необходимые типы событий, в т.ч. message_callback.

        Должен вызываться при первом деплое или смене URL.
        Пример: await MaxBotService().register_webhook("https://example.com/api/bot/webhook", secret="xxx")
        """
        if not self.settings.bot_token.strip():
            return False

        body: dict = {
            "url": url,
            "update_types": [
                "message_created",
                "message_callback",
                "bot_started",
                "bot_added",
                "bot_removed",
                "message_edited",
                "message_removed",
                "user_added",
                "user_removed",
                "chat_title_changed",
            ],
        }
        if secret:
            body["secret"] = secret

        try:
            async def _post():
                async with httpx.AsyncClient(timeout=30.0) as client:
                    return await client.post(
                        f"{BOT_API_BASE}/subscriptions",
                        headers=self._auth_headers(),
                        json=body,
                    )

            response = await self._request_with_rate_limit(_post)
            if response.is_success:
                logger.info("Webhook registered OK: url=%s", url)
                return True
            logger.warning(
                "Webhook registration failed: HTTP %s %s",
                response.status_code, response.text[:300],
            )
            return False
        except Exception as exc:
            logger.warning("Webhook registration error: %s", exc)
            return False

    async def list_subscriptions(self) -> list[dict]:
        """GET /subscriptions — webhook-подписки (содержат chat_id чатов бота)."""
        if not self.settings.bot_token.strip():
            return []

        async def _get():
            async with httpx.AsyncClient(timeout=30.0) as client:
                return await client.get(
                    f"{BOT_API_BASE}/subscriptions",
                    headers=self._auth_headers(json_body=False),
                )

        try:
            response = await self._request_with_rate_limit(_get)
        except httpx.HTTPError as exc:
            logger.warning("MAX list_subscriptions network error: %s", exc)
            return []
        if not response.is_success:
            logger.warning(
                "MAX list_subscriptions failed HTTP %s: %s",
                response.status_code,
                response.text[:300],
            )
            return []
        try:
            data = response.json()
        except ValueError:
            return []
        subs = data.get("subscriptions") if isinstance(data, dict) else None
        return subs if isinstance(subs, list) else []

    async def set_commands(self, commands: list[dict[str, str]]) -> bool:
        """
        Регистрирует slash-команды бота через PATCH /me.
        commands: [{"name": "new", "description": "..."}, ...]
        После регистрации команды появляются в меню «/» у пользователей.
        """
        if not self.settings.bot_token.strip():
            return False
        body = {"commands": commands}
        try:
            async def _patch():
                async with httpx.AsyncClient(timeout=15.0) as client:
                    return await client.patch(
                        f"{BOT_API_BASE}/me",
                        headers=self._auth_headers(),
                        json=body,
                    )

            response = await self._request_with_rate_limit(_patch)
            if response.is_success:
                logger.info("Bot commands registered: %s", [c["name"] for c in commands])
                return True
            logger.warning("set_commands failed: HTTP %s %s", response.status_code, response.text[:200])
            return False
        except Exception as exc:
            logger.warning("set_commands error: %s", exc)
            return False
