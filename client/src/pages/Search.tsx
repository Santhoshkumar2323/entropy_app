import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { searchPosts, searchUsers, type Post, type Author } from "../api";
import PostCard from "../PostCard";

export default function Search() {
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  const [tab, setTab] = useState<"posts" | "users">("posts");
  const [posts, setPosts] = useState<Post[]>([]);
  const [users, setUsers] = useState<Author[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (q.trim().length < 2) return;
    setLoading(true);
    if (tab === "posts") {
      searchPosts(q).then((r) => setPosts(r.posts)).finally(() => setLoading(false));
    } else {
      searchUsers(q).then((r) => setUsers(r.users)).finally(() => setLoading(false));
    }
  }, [q, tab]);

  function handleDeleted(id: number) {
    setPosts((prev) => prev.filter((p) => p.id !== id));
  }

  return (
    <div>
      <h2>Results for "{q}"</h2>
      <div className="tabs">
        <button className={tab === "posts" ? "active" : ""} onClick={() => setTab("posts")}>
          Posts
        </button>
        <button className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}>
          People
        </button>
      </div>

      {loading && <p>Searching...</p>}

      {!loading && tab === "posts" && posts.length === 0 && <p className="empty">No posts found.</p>}
      {!loading &&
        tab === "posts" &&
        posts.map((p) => <PostCard key={p.id} post={p} onDeleted={handleDeleted} />)}

      {!loading && tab === "users" && users.length === 0 && <p className="empty">No people found.</p>}
      {!loading && tab === "users" && (
        <div className="user-list">
          {users.map((u) => (
            <Link key={u.id} to={`/u/${u.username}`} className="user-row">
              <strong>{u.display_name}</strong> <span className="username">@{u.username}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}