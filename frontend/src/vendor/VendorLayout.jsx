import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import VendorSidebar from "./VendorSidebar";
import VendorTopbar from "./VendorTopbar";
import { VendorToastProvider } from "./VendorToastContext";

const VENDOR_THEME_KEY = "mt_vendor_theme";

function getInitialTheme() {
  if (typeof window === "undefined") return "light";
  const stored = String(window.localStorage.getItem(VENDOR_THEME_KEY) || "").trim();
  if (stored === "dark" || stored === "light") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export default function VendorLayout() {
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
    window.localStorage.setItem(VENDOR_THEME_KEY, theme);
  }, [theme]);

  return (
    <VendorToastProvider>
      <div
        className={`vendor-shell theme-${theme} ${sidebarOpen ? "sidebar-open" : ""} ${
          sidebarCollapsed ? "sidebar-collapsed" : ""
        }`}
      >
        <VendorSidebar onNavigate={handleNavigate} />
        <div className="vendor-main">
          <VendorTopbar
            onToggleSidebar={handleToggleSidebar}
            onToggleTheme={() => setTheme((prev) => (prev === "dark" ? "light" : "dark"))}
            theme={theme}
          />
          <main className="vendor-content">
            <Outlet />
          </main>
        </div>
        {sidebarOpen ? (
          <button
            type="button"
            aria-label="Close sidebar"
            className="vendor-backdrop"
            onClick={() => setSidebarOpen(false)}
          />
        ) : null}
      </div>
    </VendorToastProvider>
  );
}
