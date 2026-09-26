import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createPost, getTimeline, suggestions, follow, type Post } from "../api";
import { useAuth } from "../AuthContext";
import PostCard from "../PostCard";

interface Suggestion {
  id: number;
  username: string;
  display_name: string;
  follower_count: number;
}

export default function Home() {
  const { user } = useAuth();
  const [posts, setPosts] = useState<Post[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(true);
  const [body, setBody] = useState("");
  const [posting, setPosting] = useState(false);
  const [suggested, setSuggested] = useState<Suggestion[]>([]);

  async function loadFirstPage() {
    setLoading(true);
    const data = await getTimeline();
    setPosts(data.posts);
    setCursor(data.next_cursor);
    setHasMore(data.next_cursor !== null);
    setLoading(false);
  }

  useEffect(() => {
    if (!user) {
      setLoading(false);
      return;
    }
    loadFirstPage();
    suggestions()
      .then(setSuggested)
      .catch(() => setSuggested([]));
  }, [user]);

  async function loadMore() {
    const data = await getTimeline(cursor);
    setPosts((prev) => [...prev, ...data.posts]);
    setCursor(data.next_cursor);
    setHasMore(data.next_cursor !== null);
  }

  async function handlePost(e: React.FormEvent) {
    e.preventDefault();
    if (!body.trim() || posting) return;
    setPosting(true);
    try {
      const post = await createPost(body.trim());
      setPosts((prev) => [post, ...prev]);
      setBody("");
    } finally {
      setPosting(false);
    }
  }

  function handleDeleted(id: number) {
    setPosts((prev) => prev.filter((p) => p.id !== id));
  }

  async function handleFollow(id: number) {
    await follow(id);
    setSuggested((prev) => prev.filter((s) => s.id !== id));
    loadFirstPage();
  }

  if (!user) {
    return (
      <p>
        <Link to="/login">Log in</Link> to see your home feed.
      </p>
    );
  }

  return (
    <div className="home-layout">
      <div className="feed-column">
        <form onSubmit={handlePost} className="composer">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="What's happening?"
            maxLength={280}
            rows={3}
          />
          <div className="composer-footer">
            <span className={body.length > 260 ? "count warn" : "count"}>{body.length} / 280</span>
            <button type="submit" disabled={!body.trim() || posting}>
              Post
            </button>
          </div>
        </form>

        {loading && <p>Loading...</p>}
        {!loading && posts.length === 0 && (
          <p className="empty">
            Your feed is empty. Follow someone from the suggestions to get started.
          </p>
        )}
        {posts.map((p) => (
          <PostCard key={p.id} post={p} onDeleted={handleDeleted} />
        ))}
        {hasMore && !loading && (
          <button className="load-more" onClick={loadMore}>
            Load more
          </button>
        )}
      </div>

      {suggested.length > 0 && (
        <aside className="sidebar">
          <h3>Who to follow</h3>
          {suggested.map((s) => (
            <div key={s.id} className="suggestion-row">
              <Link to={`/u/${s.username}`}>{s.username}</Link>
              <button onClick={() => handleFollow(s.id)}>Follow</button>
            </div>
          ))}
        </aside>
      )}
    </div>
  );
}