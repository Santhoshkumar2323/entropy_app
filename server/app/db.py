from contextlib import contextmanager

import redis
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

pool = ConnectionPool(
    settings.DATABASE_URL,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row},
    open=False,
)

rds = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def open_pool() -> None:
    pool.open()
    pool.wait()


def close_pool() -> None:
    pool.close()


@contextmanager
def db():
    with pool.connection() as conn:
        yield conn


def redis_ok() -> bool:
    try:
        return bool(rds.ping())
    except redis.RedisError:
        return False


if __name__ == "__main__":
    open_pool()
    with db() as conn:
        tables = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
        ).fetchall()
    print("Postgres OK. Tables:", [t["tablename"] for t in tables])
    print("Redis OK:", redis_ok())
    close_pool()