from fastapi import APIRouter

from app.api import admin, agent, auth, bot_webhook, config, feedback, files, health, legal, payments, search, support, threads, users, voice

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(config.router)
api_router.include_router(legal.router)
api_router.include_router(auth.router)
api_router.include_router(search.router)
api_router.include_router(agent.router)
api_router.include_router(threads.router)
api_router.include_router(feedback.router)
api_router.include_router(users.router)
api_router.include_router(payments.router)
api_router.include_router(support.router)
api_router.include_router(files.router)
api_router.include_router(voice.router)
api_router.include_router(bot_webhook.router)
api_router.include_router(admin.router)
