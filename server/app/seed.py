import argparse
import random
import sys
import time
from datetime import datetime, timedelta, timezone

from faker import Faker

from .auth import hash_password
from .config import settings
from .db import close_pool, db, open_pool, rds

fake = Faker()

TOPICS = ["coding", "systemdesign", "tech", "python", "ddia", "redis",
          "postgres", "webdev", "ai", "opensource"]

TEMPLATES = [
    "Just shipped {thing}. Feeling good about it. #{tag}",
    "Anyone else struggling with {thing} today? #{tag}",
    "Hot take: {thing} is underrated. #{tag}",
    "Reading up on {thing} this weekend. #{tag} #{tag2}",
    "TIL something new about {thing}. #{tag}",
    "{thing} finally clicked for me today.",
    "Debugging {thing} for the third hour straight. #{tag}",
    "Notes from today: {thing}. #{tag} #{tag2}",
]

THINGS = ["caching", "database indexing", "load balancing", "the CAP theorem",
          "message queues", "API design", "rate limiting", "sharding",
          "async code", "unit testing", "CI pipelines", "search indexing"]


def gen_username(i: int) -> str:
    return f"{fake.user_name()}_{i}"[:20]


def gen_post_text() -> str:
    tmpl = random.choice(TEMPLATES)
    tag, tag2 = random.sample(TOPICS, 2)
    return tmpl.format(thing=random.choice(THINGS), tag=tag, tag2=tag2)


def extract_tags(text: str) -> list[str]:
    return sorted({w.lower() for w in text.split() if w.startswith("#")} and
                  {w.strip("#.,!?").lower() for w in text.split() if w.startswith("#")})


def run_seed() -> None:
    t0 = time.time()
    print(f"Seeding {settings.SEED_USERS} users and {settings.SEED_POSTS} posts...")

    with db() as conn, conn.cursor() as cur:
        # 1. Users
        pw_hash = hash_password("password123")  # same for every seed user, for easy testing
        user_ids: list[int] = []
        rows = [
            (gen_username(i), f"seed_user_{i}@example.com", pw_hash, fake.name(), fake.sentence(nb_words=8))
            for i in range(settings.SEED_USERS)
        ]
        with cur.copy(
            "COPY users (username, email, password_hash, display_name, bio, is_seed) "
            "FROM STDIN"
        ) as cp:
            for r in rows:
                cp.write_row((*r, True))
        user_ids = [
            r["id"] for r in cur.execute(
                "SELECT id FROM users WHERE is_seed = true ORDER BY id"
            ).fetchall()
        ]
        print(f"  users: {len(user_ids)}")

        # 2. Follows: each user follows 5-40 random others
        follow_rows = set()
        for uid in user_ids:
            n = random.randint(5, 40)
            for target in random.sample(user_ids, min(n, len(user_ids) - 1)):
                if target != uid:
                    follow_rows.add((uid, target))
        with cur.copy("COPY follows (follower_id, followee_id) FROM STDIN") as cp:
            for r in follow_rows:
                cp.write_row(r)
        print(f"  follows: {len(follow_rows)}")

        now = datetime.now(timezone.utc)
        post_rows = []
        for _ in range(settings.SEED_POSTS):
            author = random.choice(user_ids)
            age = timedelta(
                days=random.uniform(0, 30),
                seconds=random.randint(0, 86400),
            )
            post_rows.append((author, gen_post_text(), now - age))
        post_rows.sort(key=lambda r: r[2])  

        with cur.copy("COPY posts (user_id, body, created_at, is_seed) FROM STDIN") as cp:
            for uid, body, created in post_rows:
                cp.write_row((uid, body, created, True))

        seeded = [
            (r["id"], r["body"], r["created_at"])
            for r in cur.execute(
                "SELECT id, body, created_at FROM posts WHERE is_seed = true ORDER BY id"
            ).fetchall()
        ]
        print(f"  posts: {len(seeded)}")

        tag_rows = []
        for post_id, body, created_at in seeded:
            for word in body.split():
                if word.startswith("#"):
                    tag = word.strip("#.,!?").lower()
                    if tag:
                        tag_rows.append((post_id, tag, created_at))
        with cur.copy("COPY hashtags (post_id, tag, created_at) FROM STDIN") as cp:
            for r in set(tag_rows):
                cp.write_row(r)
        print(f"  hashtags: {len(set(tag_rows))}")

        like_rows = set()
        for post_id, _, _ in random.sample(seeded, k=len(seeded) // 2):
            for liker in random.sample(user_ids, random.randint(0, 15)):
                like_rows.add((liker, post_id))
        with cur.copy("COPY likes (user_id, post_id) FROM STDIN") as cp:
            for r in like_rows:
                cp.write_row(r)
        print(f"  likes: {len(like_rows)}")

    print(f"Done in {time.time() - t0:.1f}s")


def run_clear() -> None:
    with db() as conn:
        deleted_users = conn.execute(
            "DELETE FROM users WHERE is_seed = true RETURNING id"
        ).fetchall()
        conn.execute("DELETE FROM posts WHERE is_seed = true")
    n = len(deleted_users)

    cleared_keys = 0
    for key in rds.scan_iter("timeline:*"):
        rds.delete(key)
        cleared_keys += 1
    rds.delete("trending")

    print(f"Cleared {n} seed users (cascaded posts/follows/hashtags/likes).")
    print(f"Cleared {cleared_keys} cached timelines + trending cache.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()

    open_pool()
    try:
        run_clear() if args.clear else run_seed()
    finally:
        close_pool()