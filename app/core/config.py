"""应用配置模块。

集中声明环境变量和 `.env` 文件中的运行时配置。
"""
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用运行配置。

    配置优先来自环境变量，其次读取项目根目录下的 `.env` 文件。
    这里集中声明运行时依赖的配置项，避免业务代码直接读取环境变量。
    """

    APP_NAME: str = "DocuRAG"
    APP_ENV: str = "development"
    DEBUG: bool = False
    UPLOAD_DIR: str = "data/uploads"

    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """返回缓存后的应用配置。

    Returns:
        Settings: 当前进程复用的配置对象。
    """

    return Settings()
