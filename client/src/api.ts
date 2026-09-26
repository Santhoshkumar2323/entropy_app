const BASE = "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include", // send/receive the httpOnly cookie
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ---------- types ----------

export interface Author {
  id: number;
  username: string;
  display_name: string;
}

export interface Post {
  id: number;
  body: string;
  created_at: string;
  like_count: number;
  liked_by_me: boolean;
  author: Author;
}

export interface PostPage {
  posts: Post[];
  next_cursor: number | null;
}

export interface Profile {
  id: number;
  username: string;
  display_name: string;
  bio: string;
  created_at: string;
  post_count: number;
  follower_count: number;
  following_count: number;
  is_following: boolean;
  is_me: boolean;
}

export interface TrendingTag {
  tag: string;
  count: number;
}

// ---------- auth ----------

export const registerUser = (username: string, email: string, password: string) =>
  request<Author>("/auth/register", { method: "POST", body: JSON.stringify({ username, email, password }) });

export const login = (email: string, password: string) =>
  request<Author>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });

export const logout = () => request<{ ok: boolean }>("/auth/logout", { method: "POST" });

export const me = () => request<Author>("/auth/me");

// ---------- posts ----------

export const createPost = (body: string) =>
  request<Post>("/posts", { method: "POST", body: JSON.stringify({ body }) });

export const deletePost = (id: number) => request<{ ok: boolean }>(`/posts/${id}`, { method: "DELETE" });

export const likePost = (id: number) =>
  request<{ like_count: number; liked_by_me: boolean }>(`/posts/${id}/like`, { method: "POST" });

export const unlikePost = (id: number) =>
  request<{ like_count: number; liked_by_me: boolean }>(`/posts/${id}/like`, { method: "DELETE" });

export const getTimeline = (cursor?: number | null) =>
  request<PostPage>(`/timeline${cursor ? `?cursor=${cursor}` : ""}`);

// ---------- users ----------

export const getProfile = (username: string) => request<Profile>(`/users/${username}`);

export const getUserPosts = (username: string, cursor?: number | null) =>
  request<PostPage>(`/users/${username}/posts${cursor ? `?cursor=${cursor}` : ""}`);

export const follow = (userId: number) =>
  request<{ following: boolean; follower_count: number }>(`/users/${userId}/follow`, { method: "POST" });

export const unfollow = (userId: number) =>
  request<{ following: boolean; follower_count: number }>(`/users/${userId}/follow`, { method: "DELETE" });

export const suggestions = () =>
  request<{ id: number; username: string; display_name: string; follower_count: number }[]>(
    "/users/suggestions"
  );

// ---------- search / trending ----------

export const searchPosts = (q: string) =>
  request<{ posts: Post[]; terms: string[] }>(`/search?q=${encodeURIComponent(q)}&type=posts`);

export const searchUsers = (q: string) =>
  request<{ users: Author[] }>(`/search?q=${encodeURIComponent(q)}&type=users`);

export const getTrending = () => request<TrendingTag[]>("/trending");

export const getHashtagPosts = (tag: string, cursor?: number | null) =>
  request<PostPage>(`/hashtags/${encodeURIComponent(tag)}/posts${cursor ? `?cursor=${cursor}` : ""}`);