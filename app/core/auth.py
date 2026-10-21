"""验证单用户 DocuRAG 的 HTTP API Key。"""

import secrets

from fastapi import HTTPException, Request, status

from app.core.config import get_settings


def require_api_key(request: Request) -> None:
    """拒绝缺失或不正确的 API Key。"""

    settings = get_settings()

    if not settings.AUTH_ENABLED:
        # 仅允许在明确的测试环境中关闭鉴权。
        if settings.APP_ENV != "test":
            raise RuntimeError(
                "Disabling authentication is only allowed in test"
            )
        return

    configured = settings.DOCURAG_API_KEY

    # 配置不完整时禁止放行，而不是静默开放。
    if configured is None or not configured.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )

    supplied = request.headers.get("X-API-Key", "")

    if not secrets.compare_digest(
        supplied,
        configured.get_secret_value(),
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
