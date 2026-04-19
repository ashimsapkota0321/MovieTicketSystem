import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import VendorSidebar from "./VendorSidebar";
import VendorTopbar from "./VendorTopbar";
import VendorNotificationSidebar from "./VendorNotificationSidebar";
import { VendorToastProvider } from "./VendorToastContext";

export default function VendorLayout() {
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
    <VendorToastProvider>
      <div
        className={`vendor-shell ${sidebarOpen ? "sidebar-open" : ""} ${
          sidebarCollapsed ? "sidebar-collapsed" : ""
        }`}
      >
        <VendorSidebar onNavigate={handleNavigate} />
        <div className="vendor-main">
          <VendorTopbar
            onToggleSidebar={handleToggleSidebar}
            onOpenNotifications={() => setNotificationOpen(true)}
          />
          <main className="vendor-content">
            <Outlet />
          </main>
        </div>
        <VendorNotificationSidebar
          isOpen={notificationOpen}
          onClose={() => setNotificationOpen(false)}
        />
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
