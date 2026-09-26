import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getProfile, getUserPosts, follow, unfollow, type Profile as ProfileType, type Post } from "../api";
import { useAuth } from "../AuthContext";
import PostCard from "../PostCard";

export default function Profile() {
  const { username } = useParams<{ username: string }>();
  const { user } = useAuth();
  const [profile, setProfile] = useState<ProfileType | null>(null);
  const [posts, setPosts] = useState<Post[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!username) return;
    setNotFound(false);
    getProfile(username)
      .then(setProfile)
      .catch(() => setNotFound(true));
    getUserPosts(username).then((data) => {
      setPosts(data.posts);
      setCursor(data.next_cursor);
      setHasMore(data.next_cursor !== null);
    });
  }, [username]);

  async function loadMore() {
    if (!username) return;
    const data = await getUserPosts(username, cursor);
    setPosts((prev) => [...prev, ...data.posts]);
    setCursor(data.next_cursor);
    setHasMore(data.next_cursor !== null);
  }

  async function toggleFollow() {
    if (!profile || busy) return;
    setBusy(true);
    try {
      const result = profile.is_following ? await unfollow(profile.id) : await follow(profile.id);
      setProfile({ ...profile, is_following: result.following, follower_count: result.follower_count });
    } finally {
      setBusy(false);
    }
  }

  function handleDeleted(id: number) {
    setPosts((prev) => prev.filter((p) => p.id !== id));
  }

  if (notFound) return <p>User not found.</p>;
  if (!profile) return <p>Loading...</p>;

  return (
    <div>
      <div className="profile-header">
        <div>
          <h2>{profile.display_name}</h2>
          <span className="username">@{profile.username}</span>
        </div>
        {!profile.is_me && user && (
          <button onClick={toggleFollow} disabled={busy} className={profile.is_following ? "following" : ""}>
            {profile.is_following ? "Unfollow" : "Follow"}
          </button>
        )}
      </div>
      {profile.bio && <p className="bio">{profile.bio}</p>}
      <div className="profile-stats">
        <span>
          <strong>{profile.post_count}</strong> posts
        </span>
        <span>
          <strong>{profile.follower_count}</strong> followers
        </span>
        <span>
          <strong>{profile.following_count}</strong> following
        </span>
      </div>

      <hr />

      {posts.length === 0 && <p className="empty">No posts yet.</p>}
      {posts.map((p) => (
        <PostCard key={p.id} post={p} onDeleted={handleDeleted} />
      ))}
      {hasMore && (
        <button className="load-more" onClick={loadMore}>
          Load more
        </button>
      )}
    </div>
  );
}