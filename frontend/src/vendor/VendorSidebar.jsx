import { NavLink } from "react-router-dom";
import {
  LayoutGrid,
  CalendarDays,
  UtensilsCrossed,
  Armchair,
  Ticket,
  BadgeDollarSign,
  ShieldCheck,
  Building2,
  Users,
  Megaphone,
  Gift,
  Send,
} from "lucide-react";
import logo from "../images/logo2.png";
import { canAccessVendorFeature, isVendorOwner } from "../lib/authSession";

const navItems = [
  { label: "Dashboard", icon: LayoutGrid, to: "/vendor/dashboard", feature: "dashboard" },
  { label: "Shows", icon: CalendarDays, to: "/vendor/shows", feature: "shows" },
  { label: "Food Items", icon: UtensilsCrossed, to: "/vendor/food", feature: "food" },
  { label: "Seats", icon: Armchair, to: "/vendor/seats", feature: "seats" },
  { label: "Pricing", icon: BadgeDollarSign, to: "/vendor/pricing", feature: "pricing" },
  {
    label: "Campaigns & Promos",
    icon: Megaphone,
    to: "/vendor/campaigns-promos",
    feature: "campaigns-promos",
  },
  {
    label: "Offers",
    icon: Gift,
    to: "/vendor/offers",
    feature: "offers",
    ownerOnly: true,
  },
  { label: "Bookings", icon: Ticket, to: "/vendor/bookings", feature: "bookings" },
  { label: "Corporate & Bulk", icon: Building2, to: "/vendor/corporate-bulk", feature: "corporate-bulk" },
  { label: "Ticket Validation", icon: ShieldCheck, to: "/vendor/ticket-validation", feature: "ticket-validation" },
  { label: "Withdrawal", icon: Send, to: "/vendor/withdrawal", feature: "dashboard", ownerOnly: true },
  {
    label: "Staff Accounts",
    icon: Users,
    to: "/vendor/staff-accounts",
    feature: "staff-accounts",
    ownerOnly: true,
  },
];

export default function VendorSidebar({ onNavigate }) {
  const visibleItems = navItems.filter((item) => {
    if (item.ownerOnly && !isVendorOwner()) return false;
    return canAccessVendorFeature(item.feature);
  });

  return (
    <aside className="vendor-sidebar">
      <div className="vendor-brand">
        <img src={logo} alt="Mero Ticket Logo" className="vendor-brand-logo" />
      </div>

      <nav className="vendor-nav">
        <div className="vendor-nav-label">Main</div>
        {visibleItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.label}
              to={item.to}
              className={({ isActive }) =>
                `vendor-nav-link ${isActive ? "active" : ""}`
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

function getInitials(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) return "V";
  const parts = trimmed.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return parts
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}
