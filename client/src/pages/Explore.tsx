import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getTrending, getHashtagPosts, type TrendingTag, type Post } from "../api";
import PostCard from "../PostCard";

export default function Explore() {
  const { tag } = useParams<{ tag?: string }>();

  if (tag) return <HashtagView tag={tag} />;
  return <TrendingView />;
}

function TrendingView() {
  const [tags, setTags] = useState<TrendingTag[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getTrending()
      .then(setTags)
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p>Loading...</p>;

  return (
    <div>
      <h2>Trending, last 24h</h2>
      {tags.length === 0 && <p className="empty">Nothing trending yet.</p>}
      <div className="trending-list">
        {tags.map((t) => (
          <Link key={t.tag} to={`/tag/${t.tag}`} className="trending-row">
            <span className="tag">#{t.tag}</span>
            <span className="count">{t.count} posts</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

function HashtagView({ tag }: { tag: string }) {
  const [posts, setPosts] = useState<Post[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getHashtagPosts(tag).then((data) => {
      setPosts(data.posts);
      setCursor(data.next_cursor);
      setHasMore(data.next_cursor !== null);
      setLoading(false);
    });
  }, [tag]);

  async function loadMore() {
    const data = await getHashtagPosts(tag, cursor);
    setPosts((prev) => [...prev, ...data.posts]);
    setCursor(data.next_cursor);
    setHasMore(data.next_cursor !== null);
  }

  function handleDeleted(id: number) {
    setPosts((prev) => prev.filter((p) => p.id !== id));
  }

  return (
    <div>
      <h2>#{tag}</h2>
      <Link to="/explore">← Back to trending</Link>
      {loading && <p>Loading...</p>}
      {!loading && posts.length === 0 && <p className="empty">No posts with this tag.</p>}
      {posts.map((p) => (
        <PostCard key={p.id} post={p} onDeleted={handleDeleted} />
      ))}
      {hasMore && !loading && (
        <button className="load-more" onClick={loadMore}>
          Load more
        </button>
      )}
    </div>
  );
}