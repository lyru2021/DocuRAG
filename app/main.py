from fastapi import FastAPI

from app.core.config import get_settings
from app.api.documents import router as documents_router

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Document knowledge base API",
)

app.include_router(documents_router)

@app.get("/health",status_code=200)
def health_check():
    return {"status": "ok"}