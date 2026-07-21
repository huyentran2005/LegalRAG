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
    
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings() # type: ignore