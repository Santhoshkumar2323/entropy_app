import { useState, useRef, useEffect } from "react";
import { Link, Outlet, useNavigate } from "react-router-dom";
import { logout } from "./api";
import { useAuth } from "./AuthContext";
import Logo from "./Logo";

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
      <div className="body">
        <nav className="leftnav">
          <Link to="/">Home</Link>
          <Link to="/explore">Explore</Link>
          {user && <Link to={`/u/${user.username}`}>Profile</Link>}
        </nav>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}