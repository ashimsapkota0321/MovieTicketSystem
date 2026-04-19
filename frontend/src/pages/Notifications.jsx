import React, { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import Pagination from "../components/Pagination";
import { useNavigate } from "react-router-dom";
import { fetchNotifications, markNotificationsRead } from "../lib/catalogApi";
import { getAuthSession } from "../lib/authSession";
import { API_BASE } from "../lib/apiBase";
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

export default function Notifications() {
  const location = useLocation();
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 10;
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [markingAll, setMarkingAll] = useState(false);
  const [savingMap, setSavingMap] = useState({});
  const [error, setError] = useState("");
  const [unreadCount, setUnreadCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);

  const selectedNotificationId = useMemo(() => {
    const stateId = Number(location.state?.selectedNotificationId || 0);
    if (stateId > 0) return stateId;

    const params = new URLSearchParams(location.search || "");
    const queryId = Number(params.get("notificationId") || params.get("notification_id") || 0);
    return queryId > 0 ? queryId : 0;
  }, [location.search, location.state]);

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
        setPage(1); // Reset to first page on reload
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

  const selectedNotification = useMemo(
    () => notifications.find((item) => Number(item?.id || 0) === selectedNotificationId) || null,
    [notifications, selectedNotificationId]
  );

  const visibleNotifications = useMemo(() => {
    if (selectedNotificationId && selectedNotification) {
      return [selectedNotification];
    }
    return notifications;
  }, [notifications, selectedNotification, selectedNotificationId]);

  // Pagination logic
  const totalPages = Math.ceil(visibleNotifications.length / PAGE_SIZE) || 1;
  const paginatedNotifications = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return visibleNotifications.slice(start, start + PAGE_SIZE);
  }, [visibleNotifications, page]);

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

  const getNotificationDetailsUrl = (item) => {
    const metadata = item?.metadata && typeof item.metadata === "object" ? item.metadata : {};
    const detailsUrl = String(metadata.details_url || metadata.ticket_details_url || "").trim();
    if (detailsUrl) return detailsUrl;

    const downloadUrl = getNotificationDownloadUrl(item);
    if (downloadUrl.includes("/download/")) {
      return downloadUrl.replace("/download/", "/details/");
    }

    const reference = String(
      metadata.ticket_reference || metadata.reference || metadata.ticket_ref || ""
    ).trim();
    if (!reference) return "";
    return `${API_BASE}/api/ticket/${encodeURIComponent(reference)}/details/`;
  };

  const buildNotificationTicketContext = (item) => {
    const metadata = item?.metadata && typeof item.metadata === "object" ? item.metadata : {};
    const bookingDetail =
      metadata.booking_detail && typeof metadata.booking_detail === "object"
        ? metadata.booking_detail
        : {};

    const reference = String(
      metadata.ticket_reference ||
      metadata.reference ||
      metadata.ticket_ref ||
      bookingDetail.ticket_reference ||
      ""
    ).trim();

    const downloadUrl = getNotificationDownloadUrl(item);
    const detailsUrl = getNotificationDetailsUrl(item);
    const qrCode = String(
      metadata.qr_code ||
      metadata.ticket_qr_code ||
      bookingDetail.qr_code ||
      ""
    ).trim();

    const showDate = formatDatePart(metadata.show_start_time);
    const showTime = formatTimePart(metadata.show_start_time);
    const venue = [toText(metadata.vendor_name), showDate, showTime]
      .filter(Boolean)
      .join(", ");

    return {
      ticket: {
        reference,
        download_url: downloadUrl,
        details_url: detailsUrl,
        qr_code: qrCode || undefined,
      },
      order: {
        movie: {
          title: toText(metadata.movie_title) || toText(bookingDetail.movie),
          language: "",
          runtime: "",
          seat: toText(bookingDetail.seats) || toText(metadata.seats),
          venue,
        },
        ticketTotal: Number(bookingDetail.total || metadata?.payment?.amount || 0) || 0,
        items: [],
        foodTotal: 0,
        total: Number(bookingDetail.total || metadata?.payment?.amount || 0) || 0,
      },
    };
  };

  const handleTicketDownload = async (item) => {
    const { ticket, order } = buildNotificationTicketContext(item);
    if (!ticket?.reference && !ticket?.download_url && !ticket?.details_url) {
      setError("Ticket download is not available for this notification.");
      return;
    }

    setError("");

    const queryRef = ticket.reference ? `?ref=${encodeURIComponent(ticket.reference)}` : "";
    navigate(`/ticket-download${queryRef}`, {
      state: {
        order,
        ticket,
        autoDownload: true,
      },
    });
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
          <h1>{selectedNotification ? "Notification details" : "Notifications"}</h1>
          <p>
            {selectedNotification
              ? "Showing only the notification you selected."
              : "Offers, booking updates, and payment notices."}
          </p>
        </div>
        <div className="d-flex gap-2 flex-wrap justify-content-end">
          {selectedNotification ? (
            <button
              type="button"
              className="wf2-customerPageAction"
              onClick={() => navigate("/notifications", { replace: true })}
            >
              View all notifications
            </button>
          ) : (
            <button
              type="button"
              className="wf2-customerPageAction"
              onClick={() => navigate("/bookings/history")}
            >
              View booking history
            </button>
          )}
        </div>
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
          {!selectedNotification ? (
            <>
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
            </>
          ) : null}
          <button
            type="button"
            className="wf2-customerPageAction"
            onClick={handleMarkAll}
            disabled={selectedNotificationId ? true : !canMarkAll || markingAll}
          >
            {markingAll ? "Updating..." : "Mark all read"}
          </button>
        </div>
      </div>

      {selectedNotification ? (
        <div className="wf2-selectedNotificationBanner">
          <div>
            <strong>Selected notification</strong>
            <p className="mb-0">Only this notification is shown below.</p>
          </div>
          <button
            type="button"
            className="wf2-notificationReadBtn"
            onClick={() => navigate("/notifications", { replace: true })}
          >
            Back to all
          </button>
        </div>
      ) : null}

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
          ? paginatedNotifications.map((item) => {
              const itemId = Number(item?.id || 0);
              const isRead = Boolean(item?.is_read);
              const hasTicketDownload = Boolean(getNotificationDownloadUrl(item));
              const hasResumeContext = Boolean(getNotificationResumeContext(item));
              const resumeExpired = isResumeNotificationExpired(item);
              const isSelected = selectedNotificationId && itemId === selectedNotificationId;

              return (
                <article
                  key={itemId || `${item?.created_at || "n"}-${item?.title || "item"}`}
                  className={`wf2-notificationCard ${isRead ? "is-read" : "is-unread"} ${isSelected ? "is-selected" : ""}`}
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
                        onClick={() => handleTicketDownload(item)}
                      >
                        Download ticket
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

        {!loading && visibleNotifications.length > PAGE_SIZE ? (
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        ) : null}
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

function formatDatePart(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString();
}

function formatTimePart(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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
