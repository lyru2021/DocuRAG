from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):   #读取环境变量
    APP_NAME: str = "DocuRAG"
    APP_ENV: str = "development"
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",        #可读取.env文件中的配置
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
@lru_cache  #缓存配置
def get_settings() -> Settings:
    return Settings()