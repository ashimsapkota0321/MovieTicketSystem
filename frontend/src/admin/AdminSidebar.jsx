import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutGrid,
  Film,
  Users,
  CalendarDays,
  CalendarRange,
  Ticket,
  ShieldAlert,
  Percent,
  BarChart3,
  Clapperboard,
  Image,
  PlayCircle,
  Gift,
  Crown,
  Wallet,
} from "lucide-react";
import logo from "../images/logo2.png";

const navItems = [
  { label: "Dashboard", icon: LayoutGrid, to: "/admin/dashboard" },
  { label: "Manage Movies", icon: Film, to: "/admin/movies" },
  { label: "Review Desk", icon: ShieldAlert, to: "/admin/reviews" },
  { label: "Manage Vendors", icon: Clapperboard, to: "/admin/vendors" },
  { label: "Manage Users", icon: Users, to: "/admin/users" },
  { label: "Manage Shows", icon: CalendarDays, to: "/admin/shows" },
  { label: "Manage Schedule", icon: CalendarRange, to: "/admin/schedule" },
  { label: "Manage Banners", icon: Image, to: "/admin/banners" },
  { label: "Manage Trailers", icon: PlayCircle, to: "/admin/trailers" },
  { label: "Manage Bookings", icon: Ticket, to: "/admin/bookings" },
  { label: "Manage Coupons", icon: Percent, to: "/admin/coupons" },
  { label: "Loyalty Rules", icon: Gift, to: "/admin/loyalty" },
  { label: "Subscriptions", icon: Crown, to: "/admin/subscriptions" },
  { label: "Referrals", icon: Wallet, to: "/admin/referrals" },
  { label: "View Reports", icon: BarChart3, to: "/admin/reports" },
];

export default function AdminSidebar({ onNavigate }) {
  return (
    <aside className="admin-sidebar">
      <div className="admin-brand">
        <img src={logo} alt="Mero Ticket Logo" className="admin-brand-logo" />
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
    </aside>
  );
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
