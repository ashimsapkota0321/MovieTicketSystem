import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Bell, Menu, ChevronDown, User, Moon, Sun } from "lucide-react";
import {
  clearAuthSession,
  clearStoredRoleData,
  getAuthSession,
  isVendorOwner,
} from "../lib/authSession";

export default function VendorTopbar({ onToggleSidebar, onToggleTheme, theme = "light" }) {
  const navigate = useNavigate();
  const location = useLocation();
  const menuRef = useRef(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [vendor, setVendor] = useState(() => getStoredVendor());
  const [searchTerm, setSearchTerm] = useState("");
  const displayName = vendor?.name || vendor?.username || "Vendor";
  const actorLabel = isVendorOwner()
    ? "Vendor Admin"
    : "Staff";
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

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    setSearchTerm(params.get("q") || "");
  }, [location.search]);

  const handleSearchSubmit = () => {
    const term = searchTerm.trim();
    if (!term) return;
    const targetPath = getVendorSearchTarget(term);
    const params = new URLSearchParams();
    params.set("q", term);
    navigate(`${targetPath}?${params.toString()}`);
  };

  const handleLogout = () => {
    const auth = getAuthSession("vendor");
    const scope = auth?.scope === "session" ? "session" : "local";
    clearAuthSession({ role: "vendor", scope });
    clearStoredRoleData("vendor", { scope });
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
        <input
          type="text"
          placeholder="Search orders, shows, or customers"
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
      <div className="vendor-topbar-actions">
        <button
          type="button"
          className="vendor-icon-btn"
          title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          onClick={onToggleTheme}
        >
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
        </button>
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
              <small>{actorLabel}</small>
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
    const raw = sessionStorage.getItem("vendor") || localStorage.getItem("vendor");
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

function getVendorSearchTarget(term) {
  const value = String(term || "").toLowerCase();
  if (
    value.includes("booking") ||
    value.includes("ticket") ||
    value.includes("order") ||
    value.includes("customer")
  ) {
    return "/vendor/bookings";
  }
  if (value.includes("show") || value.includes("movie") || value.includes("schedule")) {
    return "/vendor/shows";
  }
  if (value.includes("corporate") || value.includes("bulk") || value.includes("invoice") || value.includes("quote")) {
    return "/vendor/corporate-bulk";
  }
  if (
    value.includes("promo") ||
    value.includes("campaign") ||
    value.includes("sms") ||
    value.includes("push") ||
    value.includes("discount")
  ) {
    return "/vendor/campaigns-promos";
  }
  if (value.includes("staff") || value.includes("cashier") || value.includes("manager") || value.includes("role")) {
    return "/vendor/staff-accounts";
  }
  return "/vendor/shows";
}
