import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutGrid,
  Film,
  Users,
  CalendarDays,
  CalendarRange,
  Ticket,
  BarChart3,
  Clapperboard,
  Image,
  Settings,
} from "lucide-react";
import adminLogo from "../images/admin-logo.png";

const navItems = [
  { label: "Dashboard", icon: LayoutGrid, to: "/admin/dashboard" },
  { label: "Manage Movies", icon: Film, to: "/admin/movies" },
  { label: "Manage Cast & Crew", icon: Users, to: "/admin/people" },
  { label: "Manage Vendors", icon: Clapperboard, to: "/admin/vendors" },
  { label: "Manage Users", icon: Users, to: "/admin/users" },
  { label: "Manage Shows", icon: CalendarDays, to: "/admin/shows" },
  { label: "Manage Schedule", icon: CalendarRange, to: "/admin/schedule" },
  { label: "Manage Banners", icon: Image, to: "/admin/banners" },
  { label: "Manage Bookings", icon: Ticket, to: "/admin/bookings" },
  { label: "View Reports", icon: BarChart3, to: "/admin/reports" },
];

export default function AdminSidebar({ onNavigate }) {
  const [admin, setAdmin] = useState(() => getStoredAdmin());
  const displayName =
    admin?.full_name || admin?.fullName || admin?.name || admin?.username || "Admin Control";
  const displayEmail = admin?.email || "admin@meroticket.com";
  const initials = getInitials(displayName);
  const avatarSrc = getAvatar(admin);

  useEffect(() => {
    const handleUpdate = () => setAdmin(getStoredAdmin());
    window.addEventListener("storage", handleUpdate);
    window.addEventListener("mt:admin-updated", handleUpdate);
    return () => {
      window.removeEventListener("storage", handleUpdate);
      window.removeEventListener("mt:admin-updated", handleUpdate);
    };
  }, []);

  return (
    <aside className="admin-sidebar">
      <div className="admin-brand">
        <span className="admin-brand-mark">
          <img src={adminLogo} alt="MeroTicket logo" className="admin-brand-logo" />
        </span>
        <div>
          <div className="admin-brand-name">MeroTicket</div>
          <small className="admin-brand-sub">Admin Console</small>
        </div>
      </div>

      <nav className="admin-nav">
        <div className="admin-nav-label">Main</div>
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end
              className={({ isActive }) =>
                `admin-nav-link ${isActive ? "active" : ""}`
              }
              onClick={onNavigate}
            >
              <Icon size={18} />
              {item.label}
            </NavLink>
          );
        })}
      </nav>

      <div className="admin-sidebar-footer">
        <div className="admin-avatar">
          {avatarSrc ? <img src={avatarSrc} alt="Profile avatar" /> : initials}
        </div>
        <div>
          <div className="admin-user">{displayName}</div>
          <small className="admin-email">{displayEmail}</small>
        </div>
        <button type="button" className="admin-icon-btn subtle" title="Settings">
          <Settings size={16} />
        </button>
      </div>
    </aside>
  );
}

function getStoredAdmin() {
  if (typeof window === "undefined") return null;
  try {
    return JSON.parse(localStorage.getItem("admin") || "null");
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

function getInitials(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) return "AD";
  const parts = trimmed.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return parts
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}
