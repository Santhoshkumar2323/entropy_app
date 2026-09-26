from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from . import auth, posts, search, users
from .config import settings
from .db import close_pool, db, open_pool, redis_ok


@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    with db() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch")
    yield
    close_pool()


app = FastAPI(title="Microblog API", lifespan=lifespan)

app.state.limiter = auth.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api/v1")


@api.get("/health")
def health():
    with db() as conn:
        conn.execute("SELECT 1")
    return {"ok": True, "redis": redis_ok()}


api.include_router(auth.router)
api.include_router(posts.router)
api.include_router(posts.timeline_router)
api.include_router(users.router)
api.include_router(search.router)

app.include_router(api)