"""FastAPI 应用入口。"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import auth, entries, foods, goals, health, summary, weights

app = FastAPI(
    title=settings.project_name,
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# 注意：allow_credentials=True 与 allow_origins=["*"] 不能共存，
# 浏览器会直接拒绝。这里只放行 CORS_ORIGINS 里配置的前端域。
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(goals.router)
api_router.include_router(foods.router)
api_router.include_router(entries.router)
api_router.include_router(health.router)
api_router.include_router(summary.router)
api_router.include_router(weights.router)
app.include_router(api_router)


@app.get("/health", tags=["ops"])
def health() -> dict[str, str]:
    """健康检查，给 Render 探活用。"""
    return {"status": "ok"}
