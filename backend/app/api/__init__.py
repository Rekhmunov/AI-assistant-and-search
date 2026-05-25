from fastapi import APIRouter

from app.api import admin, auth, files, payments, search, threads, users

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(search.router)
api_router.include_router(threads.router)
api_router.include_router(users.router)
api_router.include_router(payments.router)
api_router.include_router(files.router)
api_router.include_router(admin.router)
