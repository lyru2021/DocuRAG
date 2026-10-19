"""FastAPI 应用入口。

这里只负责创建应用、注册路由和提供健康检查；业务逻辑放在 API 与 service 层。
"""

from fastapi import FastAPI

from app.api.documents import router as documents_router
from app.api.papers import router as papers_router
from app.api.uploads import router as uploads_router
from app.core.config import get_settings
from app.api.tasks import router as tasks_router
from app.api.search import router as search_router
from app.api.search_orchestrated import router as orchestrated_search_router

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Document knowledge base API",
)

app.include_router(documents_router)
app.include_router(uploads_router)
app.include_router(search_router)
app.include_router(papers_router)
app.include_router(tasks_router)
app.include_router(orchestrated_search_router)


@app.get("/health", status_code=200)
def health_check():
    return {"status": "ok"}
