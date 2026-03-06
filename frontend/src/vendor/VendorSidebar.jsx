import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import {
  LayoutGrid,
  CalendarDays,
  Armchair,
  Ticket,
  Users,
  Store,
  Package,
  FileText,
  KeyRound,
  HelpCircle,
  Settings,
} from "lucide-react";

const navItems = [
  { label: "Dashboard", icon: LayoutGrid, to: "/vendor/dashboard" },
  { label: "Shows", icon: CalendarDays, to: "/vendor/shows" },
  { label: "Seats", icon: Armchair, to: "/vendor/seats" },
  { label: "Orders", icon: Ticket, disabled: true },
  { label: "Seller List", icon: Store, disabled: true },
  { label: "Customers", icon: Users, disabled: true },
  { label: "Products", icon: Package, disabled: true },
  { label: "Invoices", icon: FileText, disabled: true },
  { label: "Authentication", icon: KeyRound, disabled: true },
  { label: "Help", icon: HelpCircle, disabled: true },
  { label: "Settings", icon: Settings, disabled: true },
];

export default function VendorSidebar({ onNavigate }) {
  const [vendor, setVendor] = useState(() => getStoredVendor());
  const displayName = vendor?.name || vendor?.username || "Vendor Admin";
  const displayEmail = vendor?.email || "vendor@meroticket.com";
  const avatarSrc = getAvatar(vendor);
  const initials = getInitials(displayName);

  useEffect(() => {
    const handleUpdate = () => setVendor(getStoredVendor());
    window.addEventListener("storage", handleUpdate);
    window.addEventListener("mt:vendor-updated", handleUpdate);
    return () => {
      window.removeEventListener("storage", handleUpdate);
      window.removeEventListener("mt:vendor-updated", handleUpdate);
    };
  }, []);

  return (
    <aside className="vendor-sidebar">
      <div className="vendor-brand">
        <span className="vendor-brand-mark">B</span>
        <div>
          <div className="vendor-brand-name">Biko</div>
          <small className="vendor-brand-sub">Vendor Console</small>
        </div>
      </div>

      <nav className="vendor-nav">
        <div className="vendor-nav-label">Main</div>
        {navItems.map((item) => {
          const Icon = item.icon;
          if (item.disabled) {
            return (
              <button key={item.label} type="button" className="vendor-nav-link disabled" disabled>
                <Icon size={18} />
                {item.label}
              </button>
            );
          }
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

      <div className="vendor-sidebar-footer">
        <div className="vendor-avatar">
          {avatarSrc ? (
            <img src={avatarSrc} alt="Profile avatar" />
          ) : (
            initials
          )}
        </div>
        <div>
          <div className="vendor-user">{displayName}</div>
          <small className="vendor-email">{displayEmail}</small>
        </div>
      </div>
    </aside>
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
