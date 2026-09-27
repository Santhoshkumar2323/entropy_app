import { useState, useRef, useEffect } from "react";
import { Link, Outlet, useNavigate } from "react-router-dom";
import { logout } from "./api";
import { useAuth } from "./AuthContext";
import Logo from "./Logo";

function HomeIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 11l9-8 9 8" />
      <path d="M5 10v10h14V10" />
    </svg>
  );
}

function ExploreIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="9" />
      <path d="M15.5 8.5l-2 5-5 2 2-5z" />
    </svg>
  );
}

function ProfileIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c0-4.4 3.6-7 8-7s8 2.6 8 7" />
    </svg>
  );
}

export default function Layout() {
  const { user, setUser } = useAuth();
  const [q, setQ] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  async function handleLogout() {
    await logout();
    setUser(null);
    setMenuOpen(false);
    navigate("/login");
  }

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (q.trim()) navigate(`/search?q=${encodeURIComponent(q.trim())}`);
  }

  const initial = user?.username?.[0]?.toUpperCase() ?? "?";

  return (
    <div className="app">
      <header className="topbar">
        <Link to="/" className="brand">
          <Logo />
          <span>Entropy</span>
        </Link>
        <form onSubmit={handleSearch} className="search-form">
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search posts and people" />
        </form>
        {user ? (
          <div className="user-menu" ref={menuRef}>
            <button className="avatar-btn" onClick={() => setMenuOpen((v) => !v)}>
              <span className="avatar-circle">{initial}</span>
              {user.username}
            </button>
            {menuOpen && (
              <div className="avatar-dropdown">
                <Link to={`/u/${user.username}`} onClick={() => setMenuOpen(false)}>
                  View profile
                </Link>
                <button className="logout-item" onClick={handleLogout}>
                  Log out
                </button>
              </div>
            )}
          </div>
        ) : (
          <Link to="/login" className="login-link">Log in</Link>
        )}
      </header>

      <main className="content">
        <Outlet />
      </main>

      <nav className="bottomnav">
        <Link to="/" aria-label="Home"><HomeIcon /></Link>
        <Link to="/explore" aria-label="Explore"><ExploreIcon /></Link>
        {user && <Link to={`/u/${user.username}`} aria-label="Profile"><ProfileIcon /></Link>}
      </nav>
    </div>
  );
}