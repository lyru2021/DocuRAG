from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    description="Document knowledge base API",
)

@app.get("/health",status_code=200)
def health_check():
    return {"status": "ok"}