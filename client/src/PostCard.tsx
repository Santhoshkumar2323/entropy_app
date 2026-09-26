import { useState } from "react";
import { Link } from "react-router-dom";
import { likePost, unlikePost, deletePost, type Post } from "./api";
import { useAuth } from "./AuthContext";

export default function PostCard({ post, onDeleted }: { post: Post; onDeleted?: (id: number) => void }) {
  const { user } = useAuth();
  const [liked, setLiked] = useState(post.liked_by_me);
  const [count, setCount] = useState(post.like_count);
  const [busy, setBusy] = useState(false);

  async function toggleLike() {
    if (!user || busy) return;
    setBusy(true);
    try {
      const result = liked ? await unlikePost(post.id) : await likePost(post.id);
      setLiked(result.liked_by_me);
      setCount(result.like_count);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!confirm("Delete this post?")) return;
    await deletePost(post.id);
    onDeleted?.(post.id);
  }

  const renderedBody = post.body.split(/(\s+)/).map((word, i) =>
    word.startsWith("#") ? (
      <Link key={i} to={`/tag/${word.slice(1)}`} className="tag">
        {word}
      </Link>
    ) : (
      word
    )
  );

  return (
    <article className="post-card">
      <div className="post-header">
        <Link to={`/u/${post.author.username}`} className="author">
          {post.author.display_name}
        </Link>
        <span className="username">@{post.author.username}</span>
        <span className="time">{new Date(post.created_at).toLocaleString()}</span>
      </div>
      <p className="post-body">{renderedBody}</p>
      <div className="post-actions">
        <button onClick={toggleLike} disabled={!user || busy} className={liked ? "liked" : ""}>
          {liked ? "♥" : "♡"} {count}
        </button>
        {user?.id === post.author.id && (
          <button onClick={handleDelete} className="delete-btn">
            Delete
          </button>
        )}
      </div>
    </article>
  );
}