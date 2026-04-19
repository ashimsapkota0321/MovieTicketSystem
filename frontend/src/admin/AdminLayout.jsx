import { useState } from "react";
import { Outlet } from "react-router-dom";
import AdminSidebar from "./AdminSidebar";
import AdminTopbar from "./AdminTopbar";
import AdminNotificationSidebar from "./AdminNotificationSidebar";
import { AdminToastProvider } from "./AdminToastContext";

export default function AdminLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [notificationOpen, setNotificationOpen] = useState(false);

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

  return (
    <AdminToastProvider>
      <div
        className={`admin-shell ${sidebarOpen ? "sidebar-open" : ""} ${
          sidebarCollapsed ? "sidebar-collapsed" : ""
        }`}
      >
        <AdminSidebar onNavigate={handleNavigate} />
        <div className="admin-main">
          <AdminTopbar
            onToggleSidebar={handleToggleSidebar}
            onOpenNotifications={() => setNotificationOpen(true)}
          />
          <main className="admin-content">
            <Outlet />
          </main>
        </div>
        <AdminNotificationSidebar
          isOpen={notificationOpen}
          onClose={() => setNotificationOpen(false)}
        />
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
