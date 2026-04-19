import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, Bell, Check, Info, Trash2, X } from "lucide-react";
import { fetchNotifications, markNotificationsRead } from "../lib/catalogApi";

export default function UserNotificationSidebar({ isOpen, onClose }) {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busyMap, setBusyMap] = useState({});

  const unreadCount = useMemo(
    () => notifications.filter((item) => !item?.is_read).length,
    [notifications]
  );

  useEffect(() => {
    if (!isOpen) return;
    let active = true;

    const load = async () => {
      setLoading(true);
      try {
        const payload = await fetchNotifications({ limit: 50 });
        if (!active) return;
        setNotifications(Array.isArray(payload?.notifications) ? payload.notifications : []);
      } catch {
        if (!active) return;
        setNotifications([]);
      } finally {
        if (active) setLoading(false);
      }
    };

    load();
    return () => {
      active = false;
    };
  }, [isOpen]);

  const markOne = async (id) => {
    if (!id || busyMap[id]) return;
    setBusyMap((prev) => ({ ...prev, [id]: true }));
    try {
      await markNotificationsRead({ ids: [id] });
      setNotifications((prev) =>
        prev.map((item) => (item.id === id ? { ...item, is_read: true } : item))
      );
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("mt:notifications-updated"));
      }
    } catch {
      // no-op
    } finally {
      setBusyMap((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    }
  };

  const markAll = async () => {
    try {
      await markNotificationsRead({ all: true });
      setNotifications((prev) => prev.map((item) => ({ ...item, is_read: true })));
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("mt:notifications-updated"));
      }
    } catch {
      // no-op
    }
  };

  const removeLocal = (id) => {
    setNotifications((prev) => prev.filter((item) => item.id !== id));
  };

  const openNotification = async (item) => {
    const id = Number(item?.id || 0);
    if (!id) return;
    if (!item?.is_read) {
      await markOne(id);
    }
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("mt:notifications-updated"));
    }
    onClose?.();
    navigate("/notifications", {
      state: { selectedNotificationId: id },
    });
  };

  const getNotificationIcon = (type) => {
    const value = String(type || "").toLowerCase();
    if (value.includes("warn") || value.includes("error")) {
      return <AlertCircle size={16} className="notification-icon warning" />;
    }
    if (value.includes("success") || value.includes("done")) {
      return <Check size={16} className="notification-icon success" />;
    }
    if (value.includes("info")) {
      return <Info size={16} className="notification-icon info" />;
    }
    return <Bell size={16} className="notification-icon default" />;
  };

  return (
    <>
      <aside
        className={`admin-notification-sidebar user-notification-sidebar ${isOpen ? "open" : ""}`}
        role="complementary"
        aria-label="Notifications"
      >
        <div className="notification-header">
          <div>
            <h3>Notifications</h3>
            {unreadCount > 0 ? <span className="notification-badge">{unreadCount}</span> : null}
          </div>
          <button
            type="button"
            className="btn btn-sm admin-icon-btn"
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
              {notifications.length ? (
                notifications.map((item) => (
                  <article
                    key={item.id}
                    className={`notification-item ${!item?.is_read ? "unread" : ""}`}
                    role="button"
                    tabIndex={0}
                    onClick={() => openNotification(item)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        openNotification(item);
                      }
                    }}
                  >
                    <div className="notification-content">
                      <div className="notification-header-mini">
                        {getNotificationIcon(item?.type)}
                        <span className="notification-title">{item?.title || "Notification"}</span>
                      </div>
                      <p className="notification-message">{item?.message || ""}</p>
                      <span className="notification-time">{formatNotificationTime(item?.created_at)}</span>
                    </div>
                    <div className="notification-actions">
                      {!item?.is_read ? (
                        <button
                          type="button"
                          className="btn btn-sm admin-icon-btn"
                          title="Mark as read"
                          onClick={(event) => {
                            event.stopPropagation();
                            markOne(item.id);
                          }}
                        >
                          <Check size={14} />
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className="btn btn-sm admin-icon-btn"
                        title="Remove"
                        onClick={(event) => {
                          event.stopPropagation();
                          removeLocal(item.id);
                        }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </article>
                ))
              ) : (
                <div className="notification-empty">
                  <Bell size={32} opacity={0.4} />
                  <p>No notifications yet</p>
                </div>
              )}
            </div>

            {notifications.length ? (
              <div className="notification-footer">
                <button
                  type="button"
                  className="btn btn-sm btn-outline-light w-100"
                  onClick={markAll}
                >
                  Mark All Read
                </button>
              </div>
            ) : null}
          </>
        )}
      </aside>

      {isOpen ? (
        <div
          className="admin-notification-backdrop user-notification-backdrop"
          onClick={onClose}
          role="presentation"
        />
      ) : null}
    </>
  );
}

function formatNotificationTime(value) {
  if (!value) return "Now";
  try {
    const date = new Date(value);
    const diffMs = Date.now() - date.getTime();
    const mins = Math.floor(diffMs / 60000);
    const hours = Math.floor(diffMs / 3600000);
    const days = Math.floor(diffMs / 86400000);
    if (mins < 1) return "Now";
    if (mins < 60) return `${mins}m ago`;
    if (hours < 24) return `${hours}h ago`;
    if (days < 7) return `${days}d ago`;
    return date.toLocaleDateString();
  } catch {
    return "Recently";
  }
}