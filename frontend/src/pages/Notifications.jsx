import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchNotifications, markNotificationsRead } from "../lib/catalogApi";
import { getAuthSession } from "../lib/authSession";
import api from "../api/api";
import "../css/customerPages.css";

const EVENT_LABELS = {
  NEW_BOOKING: "Booking",
  PAYMENT_SUCCESS: "Payment",
  SHOW_UPDATE: "Show",
  MARKETING_CAMPAIGN: "Offer",
  BOOKING_CANCEL_REQUEST: "Cancel Request",
  BOOKING_RESUME_PENDING: "Resume Booking",
  BOOKING_CANCELLED: "Booking Cancelled",
  REFUND_PROCESSED: "Refund",
};

const API_BASE =
  import.meta.env.VITE_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

export default function Notifications() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [markingAll, setMarkingAll] = useState(false);
  const [savingMap, setSavingMap] = useState({});
  const [downloadingMap, setDownloadingMap] = useState({});
  const [error, setError] = useState("");
  const [unreadCount, setUnreadCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);

  useEffect(() => {
    const auth = getAuthSession("customer");
    if (!auth?.token) {
      navigate("/login", { replace: true });
      return;
    }

    let active = true;
    const loadNotifications = async () => {
      setLoading(true);
      setError("");
      try {
        const payload = await fetchNotifications({
          limit: 100,
          unread: unreadOnly ? "true" : "false",
        });
        if (!active) return;
        setNotifications(
          Array.isArray(payload?.notifications) ? payload.notifications : []
        );
        setUnreadCount(Number(payload?.unread_count || 0));
        setTotalCount(Number(payload?.total_count || 0));
      } catch (err) {
        if (!active) return;
        setNotifications([]);
        setError(err.message || "Unable to load notifications.");
      } finally {
        if (active) setLoading(false);
      }
    };

    loadNotifications();
    return () => {
      active = false;
    };
  }, [navigate, unreadOnly]);

  const canMarkAll = useMemo(
    () => notifications.some((item) => !item?.is_read),
    [notifications]
  );

  const refreshAfterMutation = async () => {
    const payload = await fetchNotifications({
      limit: 100,
      unread: unreadOnly ? "true" : "false",
    });
    setNotifications(Array.isArray(payload?.notifications) ? payload.notifications : []);
    setUnreadCount(Number(payload?.unread_count || 0));
    setTotalCount(Number(payload?.total_count || 0));
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("mt:notifications-updated"));
    }
  };

  const handleMarkAll = async () => {
    if (!canMarkAll || markingAll) return;
    setMarkingAll(true);
    setError("");
    try {
      await markNotificationsRead({ all: true });
      await refreshAfterMutation();
    } catch (err) {
      setError(err.message || "Unable to mark notifications as read.");
    } finally {
      setMarkingAll(false);
    }
  };

  const handleMarkOne = async (id) => {
    if (!id || savingMap[id]) return;
    setSavingMap((prev) => ({ ...prev, [id]: true }));
    setError("");
    try {
      await markNotificationsRead({ ids: [id] });
      await refreshAfterMutation();
    } catch (err) {
      setError(err.message || "Unable to update notification.");
    } finally {
      setSavingMap((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    }
  };

  const getNotificationDownloadUrl = (item) => {
    const metadata = item?.metadata && typeof item.metadata === "object" ? item.metadata : {};
    const metadataDownloadUrl = String(
      metadata.download_url || metadata.ticket_download_url || metadata.details_url || ""
    ).trim();
    if (metadataDownloadUrl) {
      if (metadataDownloadUrl.includes("/details/")) {
        return metadataDownloadUrl.replace("/details/", "/download/");
      }
      return metadataDownloadUrl;
    }

    const reference = String(
      metadata.ticket_reference || metadata.reference || metadata.ticket_ref || ""
    ).trim();
    if (!reference) return "";

    return `${API_BASE}/api/ticket/${encodeURIComponent(reference)}/download/`;
  };

  const extractFilenameFromDisposition = (value, fallback) => {
    const disposition = String(value || "");
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8Match?.[1]) {
      try {
        return decodeURIComponent(utf8Match[1]);
      } catch {
        return utf8Match[1];
      }
    }
    const simpleMatch = disposition.match(/filename="?([^";]+)"?/i);
    return simpleMatch?.[1] || fallback;
  };

  const handleTicketDownload = async (item) => {
    const itemId = Number(item?.id || 0);
    if (itemId && downloadingMap[itemId]) return;

    const downloadUrl = getNotificationDownloadUrl(item);
    if (!downloadUrl) {
      setError("Ticket download is not available for this notification.");
      return;
    }

    const metadata = item?.metadata && typeof item.metadata === "object" ? item.metadata : {};
    const reference = String(
      metadata.ticket_reference || metadata.reference || metadata.ticket_ref || "mero"
    ).trim();
    const defaultFilename = `ticket-${reference || "mero"}.png`;

    setError("");
    if (itemId) {
      setDownloadingMap((prev) => ({ ...prev, [itemId]: true }));
    }

    try {
      const response = await api.get(downloadUrl, { responseType: "blob" });
      const blob = response?.data;
      if (!(blob instanceof Blob)) {
        throw new Error("Invalid ticket file received.");
      }

      const filename = extractFilenameFromDisposition(
        response?.headers?.["content-disposition"],
        defaultFilename
      );
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.rel = "noopener";
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(objectUrl);
    } catch (err) {
      setError(err?.message || "Unable to download ticket right now.");
    } finally {
      if (itemId) {
        setDownloadingMap((prev) => {
          const next = { ...prev };
          delete next[itemId];
          return next;
        });
      }
    }
  };

  const getNotificationResumeContext = (item) => {
    const metadata = item?.metadata && typeof item.metadata === "object" ? item.metadata : {};
    const context = metadata?.resume_context && typeof metadata.resume_context === "object"
      ? metadata.resume_context
      : null;
    if (!context) return null;

    const selectedSeats = Array.isArray(context.selected_seats)
      ? context.selected_seats.map((seat) => String(seat || "").trim().toUpperCase()).filter(Boolean)
      : [];
    if (!selectedSeats.length) return null;

    const movieId = Number(context.movie_id || 0);
    const cinemaId = Number(context.cinema_id || 0);
    const showId = Number(context.show_id || 0);
    const date = String(context.date || "").trim();
    const time = String(context.time || "").trim();
    if (!movieId || !cinemaId || !date || !time) return null;

    return {
      movieId,
      movieTitle: String(context.movie_title || "").trim(),
      cinemaId,
      cinemaName: String(context.cinema_name || "").trim(),
      showId: showId || null,
      hall: String(context.hall || "").trim(),
      date,
      time,
      selectedSeats,
    };
  };

  const isResumeNotificationExpired = (item) => {
    const metadata = item?.metadata && typeof item.metadata === "object" ? item.metadata : {};
    const expiresAt = String(metadata?.expires_at || "").trim();
    if (!expiresAt) return false;
    const parsed = new Date(expiresAt);
    if (Number.isNaN(parsed.getTime())) return false;
    return parsed.getTime() <= Date.now();
  };

  const handleResumeBooking = async (item) => {
    const resumeContext = getNotificationResumeContext(item);
    if (!resumeContext) {
      setError("This booking continuation is no longer available.");
      return;
    }
    if (isResumeNotificationExpired(item)) {
      setError("Seat hold has expired. Please select seats again.");
      return;
    }

    const itemId = Number(item?.id || 0);
    if (itemId > 0) {
      markNotificationsRead({ ids: [itemId] }).catch(() => {});
    }

    navigate("/booking", {
      state: {
        movie: {
          id: resumeContext.movieId,
          title: resumeContext.movieTitle,
          movieId: resumeContext.movieId,
          cinemaId: resumeContext.cinemaId,
          showDate: resumeContext.date,
          showTime: resumeContext.time,
          hall: resumeContext.hall,
        },
        vendor: {
          id: resumeContext.cinemaId,
          name: resumeContext.cinemaName,
        },
        showId: resumeContext.showId,
        hall: resumeContext.hall,
        date: resumeContext.date,
        time: resumeContext.time,
        selectedSeats: resumeContext.selectedSeats,
      },
    });
  };

  return (
    <section className="wf2-customerPage">
      <div className="wf2-customerPageHead">
        <div>
          <h1>Notifications</h1>
          <p>Offers, booking updates, and payment notices.</p>
        </div>
        <button
          type="button"
          className="wf2-customerPageAction"
          onClick={() => navigate("/bookings/history")}
        >
          View booking history
        </button>
      </div>

      <div className="wf2-notificationToolbar">
        <div className="wf2-customerStats wf2-customerStatsInline">
          <div className="wf2-customerStatCard">
            <span>Total</span>
            <strong>{totalCount}</strong>
          </div>
          <div className="wf2-customerStatCard">
            <span>Unread</span>
            <strong>{unreadCount}</strong>
          </div>
        </div>

        <div className="wf2-notificationActions">
          <button
            type="button"
            className={`wf2-notificationFilter ${!unreadOnly ? "is-active" : ""}`}
            onClick={() => setUnreadOnly(false)}
          >
            All
          </button>
          <button
            type="button"
            className={`wf2-notificationFilter ${unreadOnly ? "is-active" : ""}`}
            onClick={() => setUnreadOnly(true)}
          >
            Unread
          </button>
          <button
            type="button"
            className="wf2-customerPageAction"
            onClick={handleMarkAll}
            disabled={!canMarkAll || markingAll}
          >
            {markingAll ? "Updating..." : "Mark all read"}
          </button>
        </div>
      </div>

      {error ? <div className="wf2-customerError">{error}</div> : null}

      <div className="wf2-notificationList">
        {loading ? (
          <div className="wf2-notificationEmpty">Loading notifications...</div>
        ) : null}

        {!loading && notifications.length === 0 ? (
          <div className="wf2-notificationEmpty">
            {unreadOnly ? "No unread notifications." : "No notifications yet."}
          </div>
        ) : null}

        {!loading
          ? notifications.map((item) => {
              const itemId = Number(item?.id || 0);
              const isRead = Boolean(item?.is_read);
              const hasTicketDownload = Boolean(getNotificationDownloadUrl(item));
              const hasResumeContext = Boolean(getNotificationResumeContext(item));
              const resumeExpired = isResumeNotificationExpired(item);
              return (
                <article
                  key={itemId || `${item?.created_at || "n"}-${item?.title || "item"}`}
                  className={`wf2-notificationCard ${isRead ? "is-read" : "is-unread"}`}
                >
                  <div className="wf2-notificationCardHead">
                    <span className="wf2-notificationType">
                      {formatNotificationType(item?.event_type)}
                    </span>
                    <time className="wf2-notificationTime">
                      {formatNotificationDate(item?.created_at)}
                    </time>
                  </div>
                  <h3>{item?.title || "Notification"}</h3>
                  <p>{item?.message || ""}</p>
                  <NotificationMetadata item={item} />
                  <div className="wf2-notificationCardActions">
                    {hasResumeContext ? (
                      <button
                        type="button"
                        className="wf2-notificationReadBtn wf2-notificationDownloadBtn"
                        onClick={() => handleResumeBooking(item)}
                        disabled={resumeExpired}
                      >
                        {resumeExpired ? "Hold expired" : "Continue booking"}
                      </button>
                    ) : null}
                    {hasTicketDownload ? (
                      <button
                        type="button"
                        className="wf2-notificationReadBtn wf2-notificationDownloadBtn"
                        disabled={Boolean(downloadingMap[itemId])}
                        onClick={() => handleTicketDownload(item)}
                      >
                        {downloadingMap[itemId] ? "Downloading..." : "Download ticket"}
                      </button>
                    ) : null}
                    {!isRead ? (
                      <button
                        type="button"
                        className="wf2-notificationReadBtn"
                        onClick={() => handleMarkOne(itemId)}
                        disabled={Boolean(savingMap[itemId])}
                      >
                        {savingMap[itemId] ? "Updating..." : "Mark as read"}
                      </button>
                    ) : (
                      <span className="wf2-notificationReadLabel">Read</span>
                    )}
                  </div>
                </article>
              );
            })
          : null}
      </div>
    </section>
  );
}

function formatNotificationType(value) {
  const key = String(value || "").trim().toUpperCase();
  return EVENT_LABELS[key] || "Notice";
}

function formatNotificationDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function NotificationMetadata({ item }) {
  const metadata = item?.metadata && typeof item.metadata === "object" ? item.metadata : null;
  if (!metadata) return null;

  const payment = metadata?.payment && typeof metadata.payment === "object" ? metadata.payment : null;
  const refund =
    metadata?.refund_processed && typeof metadata.refund_processed === "object"
      ? metadata.refund_processed
      : metadata?.refund && typeof metadata.refund === "object"
        ? metadata.refund
        : null;
  const rows = [
    ["Booking", toText(metadata.booking_id)],
    ["Movie", toText(metadata.movie_title)],
    ["Cinema", toText(metadata.vendor_name)],
    ["Show", formatNotificationDate(metadata.show_start_time)],
    ["Seats", toText(metadata.seat_count)],
    ["Payment Method", toText(payment?.method)],
    ["Payment Status", toText(payment?.status)],
    ["Paid Amount", toCurrency(payment?.amount)],
    ["Refund Status", toText(refund?.status || metadata?.request_status)],
    ["Refund Amount", toCurrency(refund?.refund_amount || refund?.amount)],
    ["Refund Percent", toPercent(refund?.refund_percent)],
    ["Cancellation Charge", toCurrency(refund?.cancellation_charge_amount)],
    ["Reason", toText(refund?.reason || metadata?.processed_reason || metadata?.requested_reason)],
    ["Ticket", toText(metadata.ticket_reference)],
  ].filter((entry) => !!entry[1]);

  if (rows.length === 0) return null;

  return (
    <div className="wf2-notificationMeta">
      {rows.map(([label, value]) => (
        <div key={label} className="wf2-notificationMetaItem">
          <span>{label}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  );
}

function toText(value) {
  const text = String(value ?? "").trim();
  return text || "";
}

function toCurrency(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "";
  return `NPR ${amount.toLocaleString()}`;
}

function toPercent(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "";
  return `${num}%`;
}
