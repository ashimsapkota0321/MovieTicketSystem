import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Bell, Menu, ChevronDown, User } from "lucide-react";
import { clearAuthSession, clearStoredRoleData, getAuthSession } from "../lib/authSession";

export default function AdminTopbar({ onToggleSidebar, onOpenNotifications }) {
  const navigate = useNavigate();
  const location = useLocation();
  const menuRef = useRef(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [admin, setAdmin] = useState(() => getStoredAdmin());
  const [searchTerm, setSearchTerm] = useState("");
  const displayName =
    admin?.full_name || admin?.fullName || admin?.name || admin?.username || "Admin";
  const greeting = getTimeGreeting();
  const avatarSrc = getAvatar(admin);
  const initial = getInitial(displayName || admin?.username || "A");

  useEffect(() => {
    const handleUpdate = () => setAdmin(getStoredAdmin());
    window.addEventListener("storage", handleUpdate);
    window.addEventListener("mt:admin-updated", handleUpdate);
    return () => {
      window.removeEventListener("storage", handleUpdate);
      window.removeEventListener("mt:admin-updated", handleUpdate);
    };
  }, []);

  useEffect(() => {
    const handleOutside = (event) => {
      if (!menuRef.current || menuRef.current.contains(event.target)) return;
      setMenuOpen(false);
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    setSearchTerm(params.get("q") || "");
  }, [location.search]);

  const handleSearchSubmit = () => {
    const term = searchTerm.trim();
    if (!term) return;
    const targetPath = getAdminSearchTarget(term);
    const params = new URLSearchParams();
    params.set("q", term);
    navigate(`${targetPath}?${params.toString()}`);
  };

  const handleLogout = () => {
    const auth = getAuthSession("admin");
    const scope = auth?.scope === "session" ? "session" : "local";
    clearAuthSession({ role: "admin", scope });
    clearStoredRoleData("admin", { scope });
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("mt:admin-updated"));
    }
    navigate("/login");
  };

  return (
    <header className="admin-topbar">
      <button type="button" className="admin-icon-btn" onClick={onToggleSidebar} title="Menu">
        <Menu size={18} />
      </button>

      <div className="admin-greeting">
        <small>{greeting}</small>
        <h2>{displayName}!</h2>
      </div>

      <div className="admin-search">
        <input
          type="text"
          placeholder="Search movies, vendors, users, bookings"
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              handleSearchSubmit();
            }
          }}
        />
      </div>

      <div className="admin-topbar-actions">
        <button
          type="button"
          className="admin-icon-btn"
          title="Notifications"
          onClick={onOpenNotifications}
        >
          <Bell size={18} />
        </button>
        <div className="admin-profile-menu" ref={menuRef}>
          <button
            type="button"
            className="admin-profile-chip"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="admin-profile-avatar">
              {avatarSrc ? (
                <img src={avatarSrc} alt="Profile avatar" />
              ) : initial ? (
                <span>{initial}</span>
              ) : (
                <User size={16} />
              )}
            </span>
            <div>
              <div className="admin-profile-name">{displayName}</div>
              <small>Admin</small>
            </div>
            <ChevronDown size={16} />
          </button>
          {menuOpen ? (
            <div className="admin-profile-dropdown" role="menu">
              <button
                type="button"
                className="admin-profile-item"
                onClick={() => {
                  setMenuOpen(false);
                  navigate("/admin/profile");
                }}
              >
                Profile
              </button>
              <button
                type="button"
                className="admin-profile-item"
                onClick={() => {
                  setMenuOpen(false);
                  handleLogout();
                }}
              >
                Logout
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}

function getStoredAdmin() {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(sessionStorage.getItem("admin") || localStorage.getItem("admin") || "null");
  } catch {
    return null;
  }
}

function getAvatar(user) {
  if (!user) return "";
  return (
    user.avatar ||
    user.avatarUrl ||
    user.profile_image ||
    user.profileImage ||
    user.photo ||
    user.image ||
    ""
  );
}

function getInitial(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) return "";
  return trimmed.slice(0, 1).toUpperCase();
}

function getTimeGreeting(now = new Date()) {
  const hour = now.getHours();
  if (hour < 12) return "Good Morning";
  if (hour < 18) return "Good Afternoon";
  return "Good Evening";
}

function getAdminSearchTarget(term) {
  const value = String(term || "").toLowerCase();
  if (value.includes("vendor") || value.includes("cinema") || value.includes("theatre")) {
    return "/admin/vendors";
  }
  if (value.includes("user") || value.includes("customer") || value.includes("account")) {
    return "/admin/users";
  }
  if (
    value.includes("booking") ||
    value.includes("ticket") ||
    value.includes("order") ||
    value.includes("refund") ||
    value.includes("payout") ||
    value.includes("withdraw") ||
    value.includes("review") ||
    value.includes("moderation")
  ) {
    return value.includes("payout") || value.includes("withdraw") || value.includes("review") || value.includes("moderation")
      ? "/admin/reviews"
      : "/admin/bookings";
  }
  return "/admin/movies";
}
