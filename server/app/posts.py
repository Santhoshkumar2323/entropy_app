import logging
import re
from typing import Annotated

import redis
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field

from .auth import current_user, optional_user
from .config import settings
from .db import db, rds

log = logging.getLogger("microblog")

router = APIRouter(prefix="/posts", tags=["posts"])
timeline_router = APIRouter(prefix="/timeline", tags=["timeline"])

BIGINT_MAX = 9_223_372_036_854_775_807
PostId = Annotated[int, Path(ge=1, le=BIGINT_MAX)]
HASHTAG_RE = re.compile(r"(?<!\w)#(\w{1,50})")

POST_SQL = """
SELECT p.id, p.body, p.created_at,
       u.id AS author_id, u.username, u.display_name,
       (SELECT count(*) FROM likes l WHERE l.post_id = p.id) AS like_count,
       EXISTS (SELECT 1 FROM likes l
               WHERE l.post_id = p.id AND l.user_id = %s::bigint) AS liked_by_me
FROM posts p
JOIN users u ON u.id = p.user_id
WHERE p.id = ANY(%s::bigint[])
"""


class PostIn(BaseModel):
    body: str = Field(min_length=1, max_length=settings.POST_MAX_LENGTH)



def extract_hashtags(text: str) -> list[str]:
    return sorted({t.lower() for t in HASHTAG_RE.findall(text)})


def _shape(r: dict) -> dict:
    return {
        "id": r["id"],
        "body": r["body"],
        "created_at": r["created_at"],
        "like_count": r["like_count"],
        "liked_by_me": r["liked_by_me"],
        "author": {
            "id": r["author_id"],
            "username": r["username"],
            "display_name": r["display_name"],
        },
    }


def fetch_posts(conn, ids: list[int], viewer_id: int | None) -> list[dict]:
    if not ids:
        return []
    rows = conn.execute(POST_SQL, (viewer_id, ids)).fetchall()
    by_id = {r["id"]: _shape(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def _require_post(conn, post_id: int) -> dict:
    row = conn.execute("SELECT user_id FROM posts WHERE id = %s", (post_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Post not found")
    return row


def _like_state(conn, post_id: int, user_id: int) -> dict:
    return conn.execute(
        """SELECT (SELECT count(*) FROM likes WHERE post_id = %s) AS like_count,
                  EXISTS (SELECT 1 FROM likes WHERE post_id = %s AND user_id = %s) AS liked_by_me""",
        (post_id, post_id, user_id),
    ).fetchone()



def _tl_key(user_id: int) -> str:
    return f"timeline:{user_id}"


def push_to_timelines(user_ids: list[int], post_id: int) -> None:
    if not user_ids:
        return
    try:
        pipe = rds.pipeline()
        for uid in user_ids:
            key = _tl_key(uid)
            pipe.lpushx(key, post_id)
            pipe.ltrim(key, 0, settings.TIMELINE_MAX_LEN - 1)
        pipe.execute()
    except redis.RedisError:
        log.warning("Redis unavailable: timeline fan-out skipped")


def _redis_ids(user_id: int) -> list[int]:
    try:
        return [int(i) for i in rds.lrange(_tl_key(user_id), 0, -1)]
    except redis.RedisError:
        return []


def _query_ids(conn, user_id: int, cursor: int | None, n: int) -> list[int]:
    rows = conn.execute(
        """SELECT id FROM posts
           WHERE (user_id = %(u)s
                  OR user_id IN (SELECT followee_id FROM follows WHERE follower_id = %(u)s))
             AND (%(c)s::bigint IS NULL OR id < %(c)s::bigint)
           ORDER BY id DESC
           LIMIT %(n)s""",
        {"u": user_id, "c": cursor, "n": n},
    ).fetchall()
    return [r["id"] for r in rows]


def _rebuild(conn, user_id: int) -> list[int]:
    ids = _query_ids(conn, user_id, None, settings.TIMELINE_MAX_LEN)
    if ids:
        try:
            key = _tl_key(user_id)
            pipe = rds.pipeline()
            pipe.delete(key)
            pipe.rpush(key, *ids)
            pipe.execute()
        except redis.RedisError:
            log.warning("Redis unavailable: timeline not cached")
    return ids


def _feed_ids(conn, user_id: int, cursor: int | None, limit: int) -> list[int]:
    ids = _redis_ids(user_id)
    if not ids:
        ids = _rebuild(conn, user_id)
    page = [i for i in ids if cursor is None or i < cursor][: limit + 1]
    if len(page) < limit + 1 and len(ids) >= settings.TIMELINE_MAX_LEN:
        page = _query_ids(conn, user_id, cursor, limit + 1)
    return page



@router.post("", status_code=201)
def create_post(data: PostIn, user=Depends(current_user)):
    text = data.body.strip()
    if not text:
        raise HTTPException(422, "Post cannot be empty")
    with db() as conn:
        post_id = conn.execute(
            "INSERT INTO posts (user_id, body) VALUES (%s, %s) RETURNING id",
            (user["id"], text),
        ).fetchone()["id"]
        tags = extract_hashtags(text)
        if tags:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO hashtags (post_id, tag) VALUES (%s, %s)",
                    [(post_id, t) for t in tags],
                )
        followers = [
            r["follower_id"]
            for r in conn.execute(
                "SELECT follower_id FROM follows WHERE followee_id = %s", (user["id"],)
            ).fetchall()
        ]
        post = fetch_posts(conn, [post_id], user["id"])[0]
    push_to_timelines([user["id"], *followers], post_id)  # after commit
    return post


@router.get("/{post_id}")
def get_post(post_id: PostId, user=Depends(optional_user)):
    with db() as conn:
        posts = fetch_posts(conn, [post_id], user["id"] if user else None)
    if not posts:
        raise HTTPException(404, "Post not found")
    return posts[0]


@router.delete("/{post_id}")
def delete_post(post_id: PostId, user=Depends(current_user)):
    with db() as conn:
        row = _require_post(conn, post_id)
        if row["user_id"] != user["id"]:
            raise HTTPException(403, "You can only delete your own posts")
        conn.execute("DELETE FROM posts WHERE id = %s", (post_id,))
    return {"ok": True}


@router.post("/{post_id}/like")
def like_post(post_id: PostId, user=Depends(current_user)):
    with db() as conn:
        _require_post(conn, post_id)
        conn.execute(
            "INSERT INTO likes (user_id, post_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user["id"], post_id),
        )
        return _like_state(conn, post_id, user["id"])


@router.delete("/{post_id}/like")
def unlike_post(post_id: PostId, user=Depends(current_user)):
    with db() as conn:
        _require_post(conn, post_id)
        conn.execute(
            "DELETE FROM likes WHERE user_id = %s AND post_id = %s",
            (user["id"], post_id),
        )
        return _like_state(conn, post_id, user["id"])


@timeline_router.get("")
def timeline(
    cursor: int | None = Query(None, ge=1, le=BIGINT_MAX),
    limit: int = Query(settings.TIMELINE_PAGE_SIZE, ge=1, le=50),
    user=Depends(current_user),
):
    with db() as conn:
        page = _feed_ids(conn, user["id"], cursor, limit)
        has_more = len(page) > limit
        page = page[:limit]
        posts = fetch_posts(conn, page, user["id"])
    return {"posts": posts, "next_cursor": page[-1] if has_more else None}