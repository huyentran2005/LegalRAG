from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env",extra="ignore")

    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    s3_endpoint_url: str
    s3_access_key: str
    s3_region: str = "us-east-1"
    s3_secret_key: str
    s3_bucket_name: str
    s3_secure: bool = False
    upload_temp_dir: str = "/tmp/legalrag"

    redis_url: str

    llm_provider: str = "hf"
    llm_model_name: str = "Qwen/Qwen2.5-0.5B-Instruct"
    llm_device: str = "auto"
    llm_max_new_tokens: int = 160
    llm_temperature: float = 0.2
    xai_api_key: str | None = None
    xai_base_url: str = "https://api.x.ai/v1"
    xai_model_name: str = "grok-4.3"
    gemini_api_key: str | None = None
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_model_name: str = "gemini-2.0-flash"
    
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        expanded_origins: list[str] = []
        for origin in origins:
            expanded_origins.append(origin)
            if origin.startswith("http://localhost") or origin.startswith("https://localhost"):
                expanded_origins.append(origin.replace("localhost", "127.0.0.1"))
        return list(dict.fromkeys(expanded_origins))

@lru_cache
def get_settings() -> Settings:
    return Settings() # type: ignore
