import { useEffect, useState } from "react";
import { Bell, X, Trash2, Check, AlertCircle, Info } from "lucide-react";
import { fetchNotifications, markNotificationsRead } from "../lib/catalogApi";

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
      const data = await fetchNotifications({ limit: 50, unread: true });
      setNotifications(Array.isArray(data?.notifications) ? data.notifications : []);
      setUnreadCount(data?.unread_count || 0);
    } catch {
      setNotifications([]);
      setUnreadCount(0);
    } finally {
      setLoading(false);
    }
  };

  const handleMarkAsRead = async (notifId) => {
    try {
      await markNotificationsRead({ ids: [notifId] });
      setNotifications((prev) => prev.filter((n) => n.id !== notifId));
      setUnreadCount(Math.max(0, unreadCount - 1));
    } catch {
      // Silent fail
    }
  };

  const handleDelete = async (notifId) => {
    try {
      await markNotificationsRead({ ids: [notifId] });
      setNotifications((prev) => prev.filter((n) => n.id !== notifId));
      setUnreadCount(Math.max(0, unreadCount - 1));
    } catch {
      // Silent fail
    }
  };

  const handleClearAll = async () => {
    try {
      await markNotificationsRead({ all: true });
      setNotifications([]);
      setUnreadCount(0);
    } catch {
      // Silent fail
    }
  };

  const getNotificationIcon = (notification) => {
    const tone = resolveNotificationTone(notification);
    switch (tone) {
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
                        {getNotificationIcon(notif)}
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

function resolveNotificationTone(notification) {
  const eventType = String(notification?.event_type || "").toUpperCase();
  const metaType = String(notification?.metadata?.alert_type || "").toUpperCase();
  if (metaType === "FOOD_LOW_STOCK") return "warning";
  if (["NEW_BOOKING", "PAYMENT_SUCCESS", "REFUND_PROCESSED"].includes(eventType)) return "success";
  if (["SHOW_UPDATE", "BOOKING_CANCEL_REQUEST", "BOOKING_CANCELLED", "CUSTOM_MESSAGE"].includes(eventType)) return "warning";
  return "info";
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

