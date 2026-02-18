import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, Menu, ChevronDown, User } from "lucide-react";

export default function VendorTopbar({ onToggleSidebar }) {
  const navigate = useNavigate();
  const menuRef = useRef(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [vendor, setVendor] = useState(() => getStoredVendor());
  const displayName = vendor?.name || vendor?.username || "Vendor";
  const greeting = getTimeGreeting();
  const avatarSrc = getAvatar(vendor);
  const initial = getInitial(displayName || vendor?.username || "V");

  useEffect(() => {
    const handleUpdate = () => setVendor(getStoredVendor());
    window.addEventListener("storage", handleUpdate);
    window.addEventListener("mt:vendor-updated", handleUpdate);
    return () => {
      window.removeEventListener("storage", handleUpdate);
      window.removeEventListener("mt:vendor-updated", handleUpdate);
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

  const handleLogout = () => {
    sessionStorage.removeItem("vendor");
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("mt:vendor-updated"));
    }
    navigate("/login");
  };

  return (
    <header className="vendor-topbar">
      <button type="button" className="vendor-icon-btn" onClick={onToggleSidebar} title="Menu">
        <Menu size={18} />
      </button>
      <div className="vendor-greeting">
        <small>{greeting}</small>
        <h2>{displayName}!</h2>
      </div>
      <div className="vendor-search">
        <input type="text" placeholder="Search orders, shows, or customers" />
      </div>
      <div className="vendor-topbar-actions">
        <button type="button" className="vendor-icon-btn" title="Notifications">
          <Bell size={18} />
        </button>
        <div className="vendor-profile-menu" ref={menuRef}>
          <button
            type="button"
            className="vendor-profile-chip"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="vendor-profile-avatar">
              {avatarSrc ? (
                <img src={avatarSrc} alt="Profile avatar" />
              ) : initial ? (
                <span>{initial}</span>
              ) : (
                <User size={16} />
              )}
            </span>
            <div>
              <div className="vendor-profile-name">{displayName}</div>
              <small>Vendor</small>
            </div>
            <ChevronDown size={16} />
          </button>
          {menuOpen ? (
            <div className="vendor-profile-dropdown" role="menu">
              <button
                type="button"
                className="vendor-profile-item"
                onClick={() => {
                  setMenuOpen(false);
                  navigate("/vendor/profile");
                }}
              >
                Profile
              </button>
              <button
                type="button"
                className="vendor-profile-item"
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

function getStoredVendor() {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem("vendor");
    return JSON.parse(raw || "null");
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
