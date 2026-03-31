import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import AdminSidebar from "./AdminSidebar";
import AdminTopbar from "./AdminTopbar";
import { AdminToastProvider } from "./AdminToastContext";

const ADMIN_THEME_KEY = "mt_admin_theme";

function getInitialTheme() {
  if (typeof window === "undefined") return "light";
  const stored = String(window.localStorage.getItem(ADMIN_THEME_KEY) || "").trim();
  if (stored === "dark" || stored === "light") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function AdminLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [theme, setTheme] = useState(getInitialTheme);

  const handleToggleSidebar = () => {
    if (typeof window !== "undefined" && window.matchMedia("(max-width: 1024px)").matches) {
      setSidebarOpen((open) => !open);
      return;
    }
    setSidebarCollapsed((collapsed) => !collapsed);
  };

  const handleNavigate = () => {
    if (typeof window !== "undefined" && window.matchMedia("(max-width: 1024px)").matches) {
      setSidebarOpen(false);
    }
  };

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(ADMIN_THEME_KEY, theme);
  }, [theme]);

  return (
    <AdminToastProvider>
      <div
        className={`admin-shell theme-${theme} ${sidebarOpen ? "sidebar-open" : ""} ${
          sidebarCollapsed ? "sidebar-collapsed" : ""
        }`}
      >
        <AdminSidebar onNavigate={handleNavigate} />
        <div className="admin-main">
          <AdminTopbar
            onToggleSidebar={handleToggleSidebar}
            onToggleTheme={() => setTheme((prev) => (prev === "dark" ? "light" : "dark"))}
            theme={theme}
          />
          <main className="admin-content">
            <Outlet />
          </main>
        </div>
        {sidebarOpen ? (
          <button
            type="button"
            aria-label="Close sidebar"
            className="admin-backdrop"
            onClick={() => setSidebarOpen(false)}
          />
        ) : null}
      </div>
    </AdminToastProvider>
  );
}
