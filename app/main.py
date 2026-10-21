"""FastAPI 应用入口。

这里只负责创建应用、注册路由和提供健康检查；业务逻辑放在 API 与 service 层。
"""

from fastapi import FastAPI, Depends

from app.api.documents import router as documents_router
from app.api.papers import router as papers_router
from app.api.uploads import router as uploads_router
from app.core.config import get_settings
from app.api.tasks import router as tasks_router
from app.api.search import router as search_router
from app.api.search_orchestrated import router as orchestrated_search_router
from app.api.agent import router as agent_router
from app.core.request_logging import RequestLoggingMiddleware
from app.core.auth import require_api_key

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Document knowledge base API",
)
# 为每次 HTTP 请求生成关联标识并记录结构化访问日志。
app.add_middleware(RequestLoggingMiddleware)

# 所有业务路由统一要求 API Key；/health 保持匿名。
for router in (
    agent_router,
    documents_router,
    uploads_router,
    search_router,
    papers_router,
    tasks_router,
    orchestrated_search_router,
):
    app.include_router(
        router,
        dependencies=[Depends(require_api_key)],
    )



@app.get("/health", status_code=200)
def health_check():
    return {"status": "ok"}
