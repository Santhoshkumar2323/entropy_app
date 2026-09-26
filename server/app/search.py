import json
import logging
import re
from typing import Literal

import redis
from fastapi import APIRouter, Depends, Query

from .auth import optional_user
from .config import settings
from .db import db, rds
from .posts import BIGINT_MAX, fetch_posts

log = logging.getLogger("microblog")

router = APIRouter(tags=["search"])

WORD_RE = re.compile(r"\w+")
TAG_RE = re.compile(r"\w{1,50}")
MAX_WORDS = 5
MAX_WORD_LEN = 40  
TRENDING_KEY = "trending"

POST_SEARCH_SQL = """
SELECT p.id
FROM (SELECT id, body FROM posts ORDER BY id DESC LIMIT %(scan)s) p
CROSS JOIN LATERAL (
    SELECT count(*) AS matched, sum(x.d) AS score
    FROM (
        SELECT q.lim,
               min(CASE WHEN t.word LIKE q.w || '%%' THEN 0
                        ELSE levenshtein(left(t.word, 40), q.w) END) AS d
        FROM unnest(%(words)s::text[], %(lims)s::int[]) AS q(w, lim)
        CROSS JOIN regexp_split_to_table(lower(p.body), '[^[:alnum:]_]+') AS t(word)
        WHERE t.word <> ''
        GROUP BY q.w, q.lim
    ) x
    WHERE x.d <= x.lim
) s
WHERE s.matched = %(n)s
ORDER BY s.score, p.id DESC
LIMIT %(limit)s
"""

USER_SEARCH_SQL = """
SELECT id, username, display_name
FROM users
WHERE username::text ILIKE %(pre)s
   OR display_name ILIKE %(pre)s
   OR levenshtein(left(lower(username::text), 40), %(q)s) <= %(lim)s
ORDER BY
    CASE WHEN username::text ILIKE %(pre)s THEN 0
         ELSE levenshtein(left(lower(username::text), 40), %(q)s) END,
    username
LIMIT %(limit)s
"""

TRENDING_SQL = """
SELECT tag, count(*) AS count
FROM hashtags
WHERE created_at >= now() - make_interval(hours => %(h)s::int)
GROUP BY tag
ORDER BY count DESC, tag
LIMIT %(n)s
"""


def typo_limit(word: str) -> int:
    """How many typos to forgive: none for short words, more for long ones."""
    n = len(word)
    return 0 if n <= 3 else 1 if n == 4 else 2


def query_words(q: str) -> list[str]:
    words: list[str] = []
    for w in WORD_RE.findall(q.lower()):
        w = w[:MAX_WORD_LEN]
        if w not in words:
            words.append(w)
    return words[:MAX_WORDS]


@router.get("/search")
def search(
    q: str = Query(min_length=2, max_length=100),
    kind: Literal["posts", "users"] = Query("posts", alias="type"),
    limit: int = Query(20, ge=1, le=50),
    viewer=Depends(optional_user),
):
    words = query_words(q)

    if kind == "users":
        if not words:
            return {"users": []}
        word = words[0]
        with db() as conn:
            users = conn.execute(
                USER_SEARCH_SQL,
                {
                    "pre": word.replace("_", r"\_") + "%",
                    "q": word,
                    "lim": typo_limit(word),
                    "limit": limit,
                },
            ).fetchall()
        return {"users": users}

    if not words:
        return {"posts": []}
    with db() as conn:
        rows = conn.execute(
            POST_SEARCH_SQL,
            {
                "scan": settings.SEARCH_SCAN_LIMIT,
                "words": words,
                "lims": [typo_limit(w) for w in words],
                "n": len(words),
                "limit": limit,
            },
        ).fetchall()
        posts = fetch_posts(conn, [r["id"] for r in rows], viewer["id"] if viewer else None)
    return {"posts": posts, "terms": words}  # terms lets the frontend highlight matches


@router.get("/trending")
def trending():
    try:
        cached = rds.get(TRENDING_KEY)
        if cached is not None:
            return json.loads(cached)
    except redis.RedisError:
        log.warning("Redis unavailable: trending not cached")

    with db() as conn:
        rows = conn.execute(
            TRENDING_SQL,
            {"h": settings.TRENDING_WINDOW_HOURS, "n": settings.TRENDING_TOP_N},
        ).fetchall()

    try:
        rds.set(TRENDING_KEY, json.dumps(rows), ex=settings.TRENDING_CACHE_SECONDS)
    except redis.RedisError:
        pass
    return rows


@router.get("/hashtags/{tag}/posts")
def hashtag_posts(
    tag: str,
    cursor: int | None = Query(None, ge=1, le=BIGINT_MAX),
    limit: int = Query(settings.TIMELINE_PAGE_SIZE, ge=1, le=50),
    viewer=Depends(optional_user),
):
    clean = tag.lstrip("#").lower()
    if not TAG_RE.fullmatch(clean):
        return {"posts": [], "next_cursor": None}
    with db() as conn:
        rows = conn.execute(
            """SELECT post_id AS id FROM hashtags
               WHERE tag = %(t)s
                 AND (%(c)s::bigint IS NULL OR post_id < %(c)s::bigint)
               ORDER BY post_id DESC
               LIMIT %(n)s""",
            {"t": clean, "c": cursor, "n": limit + 1},
        ).fetchall()
        ids = [r["id"] for r in rows]
        has_more = len(ids) > limit
        ids = ids[:limit]
        posts = fetch_posts(conn, ids, viewer["id"] if viewer else None)
    return {"posts": posts, "next_cursor": ids[-1] if has_more else None}