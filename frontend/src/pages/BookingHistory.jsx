import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  cancelCustomerBookingHistory,
  fetchCustomerBookingHistory,
} from "../lib/catalogApi";
import { getAuthSession } from "../lib/authSession";
import "../css/customerPages.css";

export default function BookingHistory() {
  const navigate = useNavigate();
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyBookingId, setBusyBookingId] = useState(null);

  const loadBookings = async (active = true) => {
    setLoading(true);
    setError("");
    try {
      const payload = await fetchCustomerBookingHistory();
      if (!active) return;
      setBookings(Array.isArray(payload) ? payload : []);
    } catch (err) {
      if (!active) return;
      setBookings([]);
      setError(err.message || "Unable to load booking history.");
    } finally {
      if (active) setLoading(false);
    }
  };

  useEffect(() => {
    const auth = getAuthSession("customer");
    if (!auth?.token) {
      navigate("/login", { replace: true });
      return;
    }

    let active = true;
    loadBookings(active);
    return () => {
      active = false;
    };
  }, [navigate]);

  const handleCancelRequest = async (booking) => {
    const bookingId = Number(booking?.id || 0);
    if (!bookingId || busyBookingId === bookingId) return;

    const showDate = toDate(booking?.showTime);
    if (showDate && showDate.getTime() <= Date.now()) {
      setError("Show already started. Cancellation request is not allowed.");
      return;
    }

    if (!window.confirm(`Send cancellation request for booking #${bookingId}?`)) {
      return;
    }

    setBusyBookingId(bookingId);
    setError("");
    setNotice("");
    try {
      const data = await cancelCustomerBookingHistory(bookingId);
      setNotice(
        data?.message ||
          "Cancellation request submitted. Vendor will review and process refund manually."
      );
      await loadBookings(true);
    } catch (err) {
      setError(err.message || "Unable to submit cancellation request.");
    } finally {
      setBusyBookingId(null);
    }
  };

  const summary = useMemo(() => {
    let confirmed = 0;
    let totalSpent = 0;
    let pendingPayment = 0;
    let pendingReview = 0;
    let refundProcessing = 0;
    let refunded = 0;
    bookings.forEach((item) => {
      const status = String(item?.status || "").trim().toLowerCase();
      if (status === "confirmed") confirmed += 1;
      const amount = Number(item?.total);
      if (Number.isFinite(amount)) totalSpent += amount;

      const paymentStatus = String(item?.paymentStatus || item?.payment_status || "").trim().toUpperCase();
      const refundStatus = String(item?.refundStatus || item?.refund_status || "").trim().toUpperCase();
      const cancellationStatus = String(item?.cancellation?.request_status || "").trim().toUpperCase();

      if (paymentStatus === "PENDING" || status === "pending") pendingPayment += 1;
      if (cancellationStatus === "PENDING") pendingReview += 1;
      if (refundStatus === "PENDING") refundProcessing += 1;
      if (refundStatus === "COMPLETED" || refundStatus === "REFUNDED") refunded += 1;
    });
    return {
      total: bookings.length,
      confirmed,
      totalSpent,
      pendingPayment,
      pendingReview,
      refundProcessing,
      refunded,
    };
  }, [bookings]);

  return (
    <section className="wf2-customerPage">
      <div className="wf2-customerPageHead">
        <div>
          <h1>Booking history</h1>
          <p>Your bookings, payment status, and totals.</p>
        </div>
        <button
          type="button"
          className="wf2-customerPageAction"
          onClick={() => navigate("/notifications")}
        >
          View notifications
        </button>
      </div>

      <div className="wf2-customerStats">
        <div className="wf2-customerStatCard">
          <span>Total bookings</span>
          <strong>{summary.total}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Confirmed</span>
          <strong>{summary.confirmed}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Total spent</span>
          <strong>{formatCurrency(summary.totalSpent)}</strong>
        </div>
      </div>

      <div className="wf2-lifecycleGrid">
        <div className="wf2-lifecycleCard">
          <span>Pending payment</span>
          <strong>{summary.pendingPayment}</strong>
          <p>Bookings still waiting for successful payment confirmation.</p>
        </div>
        <div className="wf2-lifecycleCard">
          <span>Pending review</span>
          <strong>{summary.pendingReview}</strong>
          <p>Cancellation requests and manual decisions that are not finished yet.</p>
        </div>
        <div className="wf2-lifecycleCard">
          <span>Refund processing</span>
          <strong>{summary.refundProcessing}</strong>
          <p>Refunds that have been requested but not completed.</p>
        </div>
        <div className="wf2-lifecycleCard">
          <span>Refunded</span>
          <strong>{summary.refunded}</strong>
          <p>Bookings with completed refunds or reversal records.</p>
        </div>
      </div>

      {error ? <div className="wf2-customerError">{error}</div> : null}
      {notice ? <div className="wf2-customerSuccess">{notice}</div> : null}

      <div className="wf2-customerTableWrap">
        <table className="wf2-customerTable">
          <thead>
            <tr>
              <th>Movie</th>
              <th>Cinema</th>
              <th>Show</th>
              <th>Seats</th>
              <th>Payment</th>
              <th>Lifecycle</th>
              <th>Status</th>
              <th>Total</th>
              <th>Booked on</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {bookings.map((booking) => {
              const bookingId = Number(booking?.id || 0);
              const isTerminalStatus = ["cancelled", "refunded"].includes(
                String(booking?.status || "").trim().toLowerCase()
              );
              const showDate = toDate(booking?.showTime);
              const isShowStarted = showDate ? showDate.getTime() <= Date.now() : true;
              const canRequestCancel = !isTerminalStatus && !isShowStarted;
              const pendingLabel =
                String(booking?.cancellation?.request_status || "").toUpperCase() === "PENDING";
              const lifecycle = getLifecycleState(booking);

              return (
                <tr key={booking.id}>
                  <td>{booking.movie || "-"}</td>
                  <td>{booking.vendor || "-"}</td>
                  <td>{formatDateTime(booking.showTime)}</td>
                  <td>{booking.seats || "-"}</td>
                  <td>{formatPayment(booking)}</td>
                  <td>
                    <span className={`wf2-notificationType ${lifecycle.className}`}>
                      {lifecycle.label}
                    </span>
                  </td>
                  <td>{booking.status || "-"}</td>
                  <td>{formatCurrency(booking.total)}</td>
                  <td>{formatDateTime(booking.createdAt)}</td>
                  <td>
                    {canRequestCancel ? (
                      <button
                        type="button"
                        className="wf2-customerPageAction"
                        onClick={() => handleCancelRequest(booking)}
                        disabled={busyBookingId === bookingId}
                      >
                        {busyBookingId === bookingId ? "Sending..." : "Request Cancel"}
                      </button>
                    ) : pendingLabel ? (
                      <span className="wf2-notificationReadLabel">Pending Approval</span>
                    ) : (
                      <span className="wf2-notificationReadLabel">Not Available</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {!loading && bookings.length === 0 ? (
              <tr>
                <td colSpan="10">No bookings yet.</td>
              </tr>
            ) : null}
            {loading ? (
              <tr>
                <td colSpan="10">Loading booking history...</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function formatCurrency(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "NPR 0";
  return `NPR ${amount.toLocaleString()}`;
}

function formatPayment(booking) {
  const method = String(booking?.paymentMethod || "").trim();
  const status = String(booking?.paymentStatus || "").trim();
  if (method && status) return `${method} (${status})`;
  if (method) return method;
  if (status) return status;
  return "Not recorded";
}

function toDate(value) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed;
}

function getLifecycleState(booking) {
  const paymentStatus = String(booking?.paymentStatus || booking?.payment_status || "").trim().toUpperCase();
  const refundStatus = String(booking?.refundStatus || booking?.refund_status || "").trim().toUpperCase();
  const cancellationStatus = String(booking?.cancellation?.request_status || "").trim().toUpperCase();
  const bookingStatus = String(booking?.status || "").trim().toUpperCase();

  if (paymentStatus === "PENDING" || bookingStatus === "PENDING") {
    return { label: "Pending payment", className: "is-unread" };
  }
  if (refundStatus === "PENDING") {
    return { label: "Refund processing", className: "is-unread" };
  }
  if (refundStatus === "COMPLETED" || refundStatus === "REFUNDED") {
    return { label: "Refunded", className: "" };
  }
  if (cancellationStatus === "PENDING") {
    return { label: "Pending review", className: "is-unread" };
  }
  if (bookingStatus === "CONFIRMED") {
    return { label: "Confirmed", className: "" };
  }
  if (bookingStatus === "CANCELLED") {
    return { label: "Cancelled", className: "" };
  }
  return { label: bookingStatus || "Unknown", className: "" };
}
