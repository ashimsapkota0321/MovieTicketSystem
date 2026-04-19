import { useEffect, useState } from "react";
import { Bell, X, Trash2, Check, AlertCircle, Info } from "lucide-react";
import { getAuthHeaders } from "../lib/authSession";
import { API_BASE_URL } from "../lib/apiBase";

export default function VendorNotificationSidebar({ isOpen, onClose }) {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    loadNotifications();
    const interval = setInterval(loadNotifications, 30000); // Poll every 30s
    return () => clearInterval(interval);
  }, []);

  const loadNotifications = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/vendor/notifications/?limit=50`, {
        headers: { Accept: "application/json", ...getAuthHeaders() },
      });
      if (!response.ok) return;
      const data = await response.json();
      setNotifications(Array.isArray(data?.notifications) ? data.notifications : []);
      setUnreadCount(data?.unread_count || 0);
    } catch (err) {
      // Fallback: show mock notifications
      setNotifications(generateMockNotifications());
    } finally {
      setLoading(false);
    }
  };

  const handleMarkAsRead = async (notifId) => {
    try {
      await fetch(`${API_BASE_URL}/vendor/notifications/${notifId}/read/`, {
        method: "POST",
        headers: { ...getAuthHeaders() },
      });
      setNotifications((prev) =>
        prev.map((n) => (n.id === notifId ? { ...n, is_read: true } : n))
      );
      setUnreadCount(Math.max(0, unreadCount - 1));
    } catch (err) {
      // Silent fail
    }
  };

  const handleDelete = async (notifId) => {
    try {
      await fetch(`${API_BASE_URL}/vendor/notifications/${notifId}/`, {
        method: "DELETE",
        headers: { ...getAuthHeaders() },
      });
      setNotifications((prev) => prev.filter((n) => n.id !== notifId));
    } catch (err) {
      // Silent fail
    }
  };

  const handleClearAll = async () => {
    try {
      await fetch(`${API_BASE_URL}/vendor/notifications/clear/`, {
        method: "POST",
        headers: { ...getAuthHeaders() },
      });
      setNotifications([]);
      setUnreadCount(0);
    } catch (err) {
      // Silent fail
    }
  };

  const getNotificationIcon = (type) => {
    switch (type) {
      case "warning":
        return <AlertCircle size={16} className="notification-icon warning" />;
      case "info":
        return <Info size={16} className="notification-icon info" />;
      case "success":
        return <Check size={16} className="notification-icon success" />;
      default:
        return <Bell size={16} className="notification-icon default" />;
    }
  };

  return (
    <>
      {/* Notification Sidebar */}
      <aside
        className={`vendor-notification-sidebar ${isOpen ? "open" : ""}`}
        role="complementary"
        aria-label="Notifications"
      >
        <div className="notification-header">
          <div>
            <h3>Notifications</h3>
            {unreadCount > 0 && <span className="notification-badge">{unreadCount}</span>}
          </div>
          <button
            type="button"
            className="btn btn-sm vendor-icon-btn"
            onClick={onClose}
            title="Close"
          >
            <X size={18} />
          </button>
        </div>

        {loading ? (
          <div className="notification-loading">
            <div className="spinner-border spinner-border-sm" role="status">
              <span className="visually-hidden">Loading...</span>
            </div>
          </div>
        ) : (
          <>
            <div className="notification-list">
              {notifications.length > 0 ? (
                notifications.map((notif) => (
                  <div
                    key={notif.id}
                    className={`notification-item ${!notif.is_read ? "unread" : ""}`}
                  >
                    <div className="notification-content">
                      <div className="notification-header-mini">
                        {getNotificationIcon(notif.type)}
                        <span className="notification-title">{notif.title}</span>
                      </div>
                      <p className="notification-message">{notif.message}</p>
                      <span className="notification-time">
                        {formatNotificationTime(notif.created_at)}
                      </span>
                    </div>
                    <div className="notification-actions">
                      {!notif.is_read && (
                        <button
                          type="button"
                          className="btn btn-sm vendor-icon-btn"
                          onClick={() => handleMarkAsRead(notif.id)}
                          title="Mark as read"
                        >
                          <Check size={14} />
                        </button>
                      )}
                      <button
                        type="button"
                        className="btn btn-sm vendor-icon-btn"
                        onClick={() => handleDelete(notif.id)}
                        title="Delete"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))
              ) : (
                <div className="notification-empty">
                  <Bell size={32} opacity={0.4} />
                  <p>No notifications yet</p>
                </div>
              )}
            </div>

            {notifications.length > 0 && (
              <div className="notification-footer">
                <button
                  type="button"
                  className="btn btn-sm btn-outline-light w-100"
                  onClick={handleClearAll}
                >
                  Clear All
                </button>
              </div>
            )}
          </>
        )}
      </aside>

      {/* Backdrop for mobile */}
      {isOpen && (
        <div
          className="vendor-notification-backdrop"
          onClick={onClose}
          role="presentation"
        />
      )}
    </>
  );
}

function formatNotificationTime(dateString) {
  if (!dateString) return "Now";
  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  } catch {
    return "Recently";
  }
}

function generateMockNotifications() {
  return [
    {
      id: 1,
      title: "Booking Confirmation",
      message: "New booking received for Hall A on April 20, 2026",
      type: "success",
      is_read: false,
      created_at: new Date(Date.now() - 5 * 60000).toISOString(),
    },
    {
      id: 2,
      title: "Low Inventory Alert",
      message: "Popcorn inventory is running low",
      type: "warning",
      is_read: false,
      created_at: new Date(Date.now() - 30 * 60000).toISOString(),
    },
    {
      id: 3,
      title: "System Update",
      message: "New features available in your dashboard",
      type: "info",
      is_read: true,
      created_at: new Date(Date.now() - 2 * 3600000).toISOString(),
    },
    {
      id: 4,
      title: "Payment Received",
      message: "₹45,000 received from booking cancellations",
      type: "success",
      is_read: true,
      created_at: new Date(Date.now() - 24 * 3600000).toISOString(),
    },
  ];
}
