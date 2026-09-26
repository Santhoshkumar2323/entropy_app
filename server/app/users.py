import logging
from typing import Annotated

import redis
from fastapi import APIRouter, Depends, HTTPException, Path, Query

from .auth import current_user, optional_user
from .config import settings
from .db import db, rds
from .posts import BIGINT_MAX, fetch_posts

log = logging.getLogger("microblog")

router = APIRouter(prefix="/users", tags=["users"])
UserId = Annotated[int, Path(ge=1, le=BIGINT_MAX)]

PROFILE_SQL = """
SELECT u.id, u.username, u.display_name, u.bio, u.created_at,
       (SELECT count(*) FROM posts   WHERE user_id = u.id)     AS post_count,
       (SELECT count(*) FROM follows WHERE followee_id = u.id) AS follower_count,
       (SELECT count(*) FROM follows WHERE follower_id = u.id) AS following_count,
       EXISTS (SELECT 1 FROM follows
               WHERE follower_id = %s::bigint AND followee_id = u.id) AS is_following
FROM users u
WHERE u.username = %s
"""


def _drop_timeline(user_id: int) -> None:
    try:
        rds.delete(f"timeline:{user_id}")
    except redis.RedisError:
        log.warning("Redis unavailable: timeline cache not cleared")


def _follower_count(conn, user_id: int) -> int:
    return conn.execute(
        "SELECT count(*) AS n FROM follows WHERE followee_id = %s", (user_id,)
    ).fetchone()["n"]


@router.get("/suggestions")
def suggestions(limit: int = Query(5, ge=1, le=20), me=Depends(current_user)):
    with db() as conn:
        return conn.execute(
            """SELECT u.id, u.username, u.display_name,
                      (SELECT count(*) FROM follows f WHERE f.followee_id = u.id) AS follower_count
               FROM users u
               WHERE u.id <> %(me)s
                 AND NOT EXISTS (SELECT 1 FROM follows
                                 WHERE follower_id = %(me)s AND followee_id = u.id)
               ORDER BY follower_count DESC, u.id
               LIMIT %(n)s""",
            {"me": me["id"], "n": limit},
        ).fetchall()


@router.get("/{username}")
def profile(username: str, viewer=Depends(optional_user)):
    viewer_id = viewer["id"] if viewer else None
    with db() as conn:
        row = conn.execute(PROFILE_SQL, (viewer_id, username)).fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    row["is_me"] = viewer_id == row["id"]
    return row


@router.get("/{username}/posts")
def user_posts(
    username: str,
    cursor: int | None = Query(None, ge=1, le=BIGINT_MAX),
    limit: int = Query(settings.TIMELINE_PAGE_SIZE, ge=1, le=50),
    viewer=Depends(optional_user),
):
    with db() as conn:
        user = conn.execute("SELECT id FROM users WHERE username = %s", (username,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")
        rows = conn.execute(
            """SELECT id FROM posts
               WHERE user_id = %(u)s
                 AND (%(c)s::bigint IS NULL OR id < %(c)s::bigint)
               ORDER BY id DESC
               LIMIT %(n)s""",
            {"u": user["id"], "c": cursor, "n": limit + 1},
        ).fetchall()
        ids = [r["id"] for r in rows]
        has_more = len(ids) > limit
        ids = ids[:limit]
        posts = fetch_posts(conn, ids, viewer["id"] if viewer else None)
    return {"posts": posts, "next_cursor": ids[-1] if has_more else None}


@router.post("/{user_id}/follow")
def follow(user_id: UserId, me=Depends(current_user)):
    if user_id == me["id"]:
        raise HTTPException(400, "You cannot follow yourself")
    with db() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE id = %s", (user_id,)).fetchone():
            raise HTTPException(404, "User not found")
        conn.execute(
            "INSERT INTO follows (follower_id, followee_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (me["id"], user_id),
        )
        count = _follower_count(conn, user_id)
    _drop_timeline(me["id"])
    return {"following": True, "follower_count": count}


@router.delete("/{user_id}/follow")
def unfollow(user_id: UserId, me=Depends(current_user)):
    with db() as conn:
        if not conn.execute("SELECT 1 FROM users WHERE id = %s", (user_id,)).fetchone():
            raise HTTPException(404, "User not found")
        conn.execute(
            "DELETE FROM follows WHERE follower_id = %s AND followee_id = %s",
            (me["id"], user_id),
        )
        count = _follower_count(conn, user_id)
    _drop_timeline(me["id"])
    return {"following": False, "follower_count": count}