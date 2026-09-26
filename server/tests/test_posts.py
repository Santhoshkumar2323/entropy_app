import redis as redis_lib

from app.db import db, rds
from app.posts import extract_hashtags

REGISTER = "/api/v1/auth/register"
POSTS = "/api/v1/posts"
TIMELINE = "/api/v1/timeline"


def post(client, body="hello world"):
    r = client.post(POSTS, json={"body": body})
    assert r.status_code == 201, r.text
    return r.json()


def second_user(new_client, name="bob"):
    c = new_client()
    r = c.post(
        REGISTER,
        json={"username": name, "email": f"{name}@example.com", "password": "password123"},
    )
    assert r.status_code == 201, r.text
    return c


class DeadRedis:
    def __getattr__(self, name):
        def boom(*args, **kwargs):
            raise redis_lib.ConnectionError("redis is down")

        return boom


def test_extract_hashtags():
    assert extract_hashtags("#Python, #python! a#b #x_1 # #coding") == ["coding", "python", "x_1"]


def test_create_post_saves_hashtags(client, make_user):
    make_user()
    p = post(client, "Learning #Python and #python with #coding")
    assert p["author"]["username"] == "alice"
    assert p["like_count"] == 0 and p["liked_by_me"] is False
    with db() as conn:
        tags = [
            r["tag"]
            for r in conn.execute(
                "SELECT tag FROM hashtags WHERE post_id = %s ORDER BY tag", (p["id"],)
            )
        ]
    assert tags == ["coding", "python"]


def test_post_length_rules(client, make_user):
    make_user()
    assert client.post(POSTS, json={"body": ""}).status_code == 422
    assert client.post(POSTS, json={"body": "   "}).status_code == 422
    assert client.post(POSTS, json={"body": "a" * 281}).status_code == 422
    assert client.post(POSTS, json={"body": "a" * 280}).status_code == 201


def test_posting_requires_login(client):
    assert client.post(POSTS, json={"body": "hi"}).status_code == 401


def test_get_single_post(client, make_user, new_client):
    make_user()
    p = post(client, "readable by anyone")
    guest = new_client()
    r = guest.get(f"{POSTS}/{p['id']}")
    assert r.status_code == 200
    assert r.json()["body"] == "readable by anyone"
    assert client.get(f"{POSTS}/99999").status_code == 404


def test_only_owner_can_delete(client, make_user, new_client):
    make_user()
    p = post(client)
    bob = second_user(new_client)
    assert bob.delete(f"{POSTS}/{p['id']}").status_code == 403
    assert client.delete(f"{POSTS}/{p['id']}").status_code == 200
    assert client.get(f"{POSTS}/{p['id']}").status_code == 404
    assert client.delete(f"{POSTS}/{p['id']}").status_code == 404



def test_timeline_requires_login(client):
    assert client.get(TIMELINE).status_code == 401


def test_timeline_cache_is_built_then_updated(client, make_user):
    user = make_user()
    key = f"timeline:{user['id']}"
    first = post(client, "first")

    data = client.get(TIMELINE).json()  # cold: rebuilt from Postgres and cached
    assert [p["id"] for p in data["posts"]] == [first["id"]]
    assert rds.lrange(key, 0, -1) == [str(first["id"])]

    second = post(client, "second")  # warm: pushed straight into Redis
    assert rds.lrange(key, 0, -1) == [str(second["id"]), str(first["id"])]


def test_timeline_is_newest_first(client, make_user):
    make_user()
    ids = [post(client, f"post {i}")["id"] for i in range(3)]
    data = client.get(TIMELINE).json()
    assert [p["id"] for p in data["posts"]] == list(reversed(ids))
    assert data["next_cursor"] is None


def test_cursor_pagination_has_no_gaps_or_duplicates(client, make_user):
    make_user()
    created = [post(client, f"post {i}")["id"] for i in range(25)]
    seen, cursor, pages = [], None, 0
    while True:
        params = {"limit": 10}
        if cursor:
            params["cursor"] = cursor
        data = client.get(TIMELINE, params=params).json()
        seen += [p["id"] for p in data["posts"]]
        pages += 1
        cursor = data["next_cursor"]
        if cursor is None:
            break
    assert pages == 3
    assert seen == sorted(created, reverse=True)


def test_deleted_post_disappears_from_feed(client, make_user):
    make_user()
    a = post(client, "a")
    b = post(client, "b")
    client.get(TIMELINE)  
    client.delete(f"{POSTS}/{a['id']}")
    data = client.get(TIMELINE).json()
    assert [p["id"] for p in data["posts"]] == [b["id"]]


def test_feed_rebuilds_after_redis_is_wiped(client, make_user):
    user = make_user()
    ids = [post(client, f"post {i}")["id"] for i in range(3)]
    client.get(TIMELINE)
    rds.flushdb()
    data = client.get(TIMELINE).json()
    assert [p["id"] for p in data["posts"]] == list(reversed(ids))
    assert rds.llen(f"timeline:{user['id']}") == 3


def test_feed_works_without_redis(client, make_user, monkeypatch):
    make_user()
    post(client, "one")
    monkeypatch.setattr("app.posts.rds", DeadRedis())
    post(client, "two")  # fan-out is skipped quietly, no crash
    data = client.get(TIMELINE).json()
    assert [p["body"] for p in data["posts"]] == ["two", "one"]



def test_like_and_unlike(client, make_user):
    make_user()
    p = post(client)
    url = f"{POSTS}/{p['id']}/like"
    assert client.post(url).json() == {"like_count": 1, "liked_by_me": True}
    assert client.post(url).json() == {"like_count": 1, "liked_by_me": True}  # no double count
    assert client.delete(url).json() == {"like_count": 0, "liked_by_me": False}
    assert client.delete(url).json() == {"like_count": 0, "liked_by_me": False}


def test_liked_by_me_depends_on_who_is_looking(client, make_user, new_client):
    make_user()
    p = post(client)
    client.post(f"{POSTS}/{p['id']}/like")

    bob = second_user(new_client)
    seen = bob.get(f"{POSTS}/{p['id']}").json()
    assert seen["like_count"] == 1 and seen["liked_by_me"] is False

    bob.post(f"{POSTS}/{p['id']}/like")
    assert client.get(f"{POSTS}/{p['id']}").json()["like_count"] == 2
    assert client.get(f"{POSTS}/{p['id']}").json()["liked_by_me"] is True


def test_like_rules(client, make_user, new_client):
    assert new_client().post(f"{POSTS}/1/like").status_code == 401
    make_user()
    assert client.post(f"{POSTS}/99999/like").status_code == 404




USERS = "/api/v1/users"


def test_profile_and_counts(client, make_user, new_client):
    alice = make_user()
    post(client, "one")
    post(client, "two")
    bob = second_user(new_client)
    bob.post(f"{USERS}/{alice['id']}/follow")

    p = client.get(f"{USERS}/alice").json()
    assert p["username"] == "alice"
    assert p["post_count"] == 2
    assert p["follower_count"] == 1
    assert p["following_count"] == 0
    assert p["is_me"] is True and p["is_following"] is False
    assert "email" not in p and "password_hash" not in p

    seen_by_bob = bob.get(f"{USERS}/ALICE").json()  # usernames are case-insensitive
    assert seen_by_bob["is_me"] is False and seen_by_bob["is_following"] is True


def test_profile_unknown_and_guest_view(client, make_user, new_client):
    make_user()
    assert client.get(f"{USERS}/ghost").status_code == 404
    guest = new_client()
    r = guest.get(f"{USERS}/alice")
    assert r.status_code == 200
    assert r.json()["is_me"] is False and r.json()["is_following"] is False


def test_follow_and_unfollow(client, make_user, new_client):
    alice = make_user()
    bob = second_user(new_client)
    url = f"{USERS}/{alice['id']}/follow"
    assert bob.post(url).json() == {"following": True, "follower_count": 1}
    assert bob.post(url).json() == {"following": True, "follower_count": 1}  # no double count
    assert bob.delete(url).json() == {"following": False, "follower_count": 0}
    assert bob.delete(url).json() == {"following": False, "follower_count": 0}


def test_follow_rules(client, make_user, new_client):
    alice = make_user()
    assert client.post(f"{USERS}/{alice['id']}/follow").status_code == 400  # yourself
    assert client.post(f"{USERS}/99999/follow").status_code == 404
    assert client.delete(f"{USERS}/99999/follow").status_code == 404
    assert new_client().post(f"{USERS}/{alice['id']}/follow").status_code == 401


def test_follow_updates_feed(client, make_user, new_client):
    alice = make_user()
    a1 = post(client, "alice one")
    bob = second_user(new_client)
    b1 = bob.post(POSTS, json={"body": "bob one"}).json()
    assert [p["id"] for p in bob.get(TIMELINE).json()["posts"]] == [b1["id"]]  # feed is cached

    bob.post(f"{USERS}/{alice['id']}/follow")
    feed = [p["id"] for p in bob.get(TIMELINE).json()["posts"]]
    assert feed == [b1["id"], a1["id"]]  # alice's older post shows up straight away

    a2 = post(client, "alice two")  # new post is pushed into bob's cached feed
    feed = [p["id"] for p in bob.get(TIMELINE).json()["posts"]]
    assert feed == [a2["id"], b1["id"], a1["id"]]


def test_unfollow_removes_posts_from_feed(client, make_user, new_client):
    alice = make_user()
    post(client, "alice one")
    bob = second_user(new_client)
    b1 = bob.post(POSTS, json={"body": "bob one"}).json()
    bob.post(f"{USERS}/{alice['id']}/follow")
    assert len(bob.get(TIMELINE).json()["posts"]) == 2

    bob.delete(f"{USERS}/{alice['id']}/follow")
    assert [p["id"] for p in bob.get(TIMELINE).json()["posts"]] == [b1["id"]]


def test_user_posts_paginated(client, make_user, new_client):
    make_user()
    ids = [post(client, f"post {i}")["id"] for i in range(3)]
    guest = new_client()

    page1 = guest.get(f"{USERS}/alice/posts", params={"limit": 2}).json()
    assert [p["id"] for p in page1["posts"]] == [ids[2], ids[1]]
    assert page1["next_cursor"] == ids[1]

    page2 = guest.get(
        f"{USERS}/alice/posts", params={"limit": 2, "cursor": page1["next_cursor"]}
    ).json()
    assert [p["id"] for p in page2["posts"]] == [ids[0]]
    assert page2["next_cursor"] is None
    assert guest.get(f"{USERS}/ghost/posts").status_code == 404


def test_suggestions(client, make_user, new_client):
    make_user("alice")
    bob = second_user(new_client, "bob")
    second_user(new_client, "carol")
    bob_id = bob.get("/api/v1/auth/me").json()["id"]

    client.post(f"{USERS}/{bob_id}/follow")
    names = [u["username"] for u in client.get(f"{USERS}/suggestions").json()]
    assert names == ["carol"]  # not yourself, not people you already follow
    assert new_client().get(f"{USERS}/suggestions").status_code == 401   



SEARCH = "/api/v1/search"
TRENDING = "/api/v1/trending"
HASHTAGS = "/api/v1/hashtags"


def search(c, q, kind="posts"):
    r = c.get(SEARCH, params={"q": q, "type": kind})
    assert r.status_code == 200, r.text
    return r.json()


def test_search_finds_typos(client, make_user):
    make_user()
    p1 = post(client, "Learning system design today")
    p2 = post(client, "Software architecture notes")
    assert [p["id"] for p in search(client, "sytsm")["posts"]] == [p1["id"]]
    assert [p["id"] for p in search(client, "archtecture")["posts"]] == [p2["id"]]


def test_search_prefix_and_multiple_words(client, make_user):
    make_user()
    both = post(client, "System architecture basics")
    only = post(client, "System of a down")
    assert {p["id"] for p in search(client, "sys")["posts"]} == {both["id"], only["id"]}
    assert [p["id"] for p in search(client, "system archtecture")["posts"]] == [both["id"]]


def test_search_has_no_false_matches(client, make_user):
    make_user()
    post(client, "Learning system design today")
    post(client, "The car is red")
    assert search(client, "banana")["posts"] == []
    assert search(client, "cat")["posts"] == []  # short words get no typo tolerance


def test_search_deleted_post_disappears(client, make_user):
    make_user()
    p = post(client, "Unique zebra sighting")
    assert len(search(client, "zebra")["posts"]) == 1
    client.delete(f"{POSTS}/{p['id']}")
    assert search(client, "zebra")["posts"] == []


def test_search_users(client, make_user, new_client):
    make_user("alice")
    second_user(new_client, "bobby")
    guest = new_client()
    by_prefix = search(guest, "alic", "users")["users"]
    assert [u["username"] for u in by_prefix] == ["alice"]
    by_typo = search(guest, "alise", "users")["users"]
    assert [u["username"] for u in by_typo] == ["alice"]
    assert "email" not in by_prefix[0]


def test_search_validation(client):
    assert client.get(SEARCH, params={"q": "a"}).status_code == 422
    assert client.get(SEARCH, params={"q": "zebra", "type": "cats"}).status_code == 422
    assert client.get(SEARCH, params={"q": "!!!"}).json() == {"posts": []}


def test_trending_counts_and_window(client, make_user):
    make_user()
    post(client, "one #coding #tech")
    post(client, "two #coding")
    post(client, "three #coding #python")
    post(client, "ancient #old")
    with db() as conn:
        conn.execute(
            "UPDATE hashtags SET created_at = now() - interval '2 days' WHERE tag = 'old'"
        )
    assert client.get(TRENDING).json() == [
        {"tag": "coding", "count": 3},
        {"tag": "python", "count": 1},
        {"tag": "tech", "count": 1},
    ]


def test_trending_is_cached(client, make_user):
    make_user()
    post(client, "first #coding")
    assert client.get(TRENDING).json() == [{"tag": "coding", "count": 1}]
    post(client, "second #coding")
    assert client.get(TRENDING).json() == [{"tag": "coding", "count": 1}]  # from cache
    rds.flushdb()
    assert client.get(TRENDING).json() == [{"tag": "coding", "count": 2}]


def test_hashtag_page(client, make_user):
    make_user()
    a = post(client, "one #Coding")
    post(client, "two #tech")
    b = post(client, "three #coding again")

    r = client.get(f"{HASHTAGS}/coding/posts").json()
    assert [p["id"] for p in r["posts"]] == [b["id"], a["id"]]
    assert client.get(f"{HASHTAGS}/%23CODING/posts").json()["posts"][0]["id"] == b["id"]
    assert client.get(f"{HASHTAGS}/nothing/posts").json() == {"posts": [], "next_cursor": None}

    page = client.get(f"{HASHTAGS}/coding/posts", params={"limit": 1}).json()
    assert len(page["posts"]) == 1 and page["next_cursor"] == b["id"]     