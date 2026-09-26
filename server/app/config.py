import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


class Settings:
    DATABASE_URL = _env("DATABASE_URL", "postgresql://microblog:microblog@localhost:5432/microblog")
    REDIS_URL = _env("REDIS_URL", "redis://localhost:6379/0")
    CORS_ORIGINS = _env("CORS_ORIGINS", "http://localhost:5173").split(",")

    JWT_SECRET = _env("JWT_SECRET", "dev-secret-change-me")
    JWT_EXPIRE_HOURS = int(_env("JWT_EXPIRE_HOURS", "168"))
    COOKIE_SECURE = _env("COOKIE_SECURE", "false").lower() == "true"
    LOGIN_RATE_LIMIT = _env("LOGIN_RATE_LIMIT", "5/minute")

    POST_MAX_LENGTH = 280
    TIMELINE_PAGE_SIZE = 20
    TIMELINE_MAX_LEN = 800

    TRENDING_WINDOW_HOURS = 24
    TRENDING_TOP_N = 5
    TRENDING_CACHE_SECONDS = 300
    SEARCH_SCAN_LIMIT = 20000  
    
    SEED_USERS = 500
    SEED_POSTS = 5000


settings = Settings()