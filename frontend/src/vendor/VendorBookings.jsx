import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Eye, ReceiptText, Trash2, XCircle } from "lucide-react";
import {
  cancelVendorBooking,
  deleteVendorBooking,
  fetchVendorBooking,
  fetchVendorBookings,
  refundVendorBooking,
} from "../lib/catalogApi";
import { useVendorToast } from "./VendorToastContext";

export default function VendorBookings() {
  const [bookings, setBookings] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState("");
  const [busyActionId, setBusyActionId] = useState(null);
  const [searchParams] = useSearchParams();
  const { pushToast } = useVendorToast();
  const queryFromUrl = String(searchParams.get("q") || "");

  useEffect(() => {
    setQuery(queryFromUrl);
  }, [queryFromUrl]);

  const loadBookings = async () => {
    setIsLoading(true);
    try {
      const list = await fetchVendorBookings();
      setBookings(Array.isArray(list) ? list : []);
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Bookings failed",
        message: err.message || "Unable to load bookings.",
      });
      setBookings([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadBookings();
  }, []);

  const filteredBookings = useMemo(() => {
    const text = String(query || "").trim().toLowerCase();
    if (!text) return bookings;
    return bookings.filter((booking) => {
      const haystack = [
        booking?.id,
        booking?.user,
        booking?.movie,
        booking?.showTime,
        booking?.seats,
        booking?.status,
      ]
        .map((value) => String(value || "").toLowerCase())
        .join(" ");
      return haystack.includes(text);
    });
  }, [bookings, query]);

  const openDetail = async (booking) => {
    if (!booking?.id) return;
    try {
      const detail = await fetchVendorBooking(booking.id);
      setSelected(detail || booking);
    } catch {
      setSelected(booking);
    }
  };

  const isActionBusy = (bookingId) => busyActionId === bookingId;

  const handleCancel = async (booking) => {
    if (!booking?.id) return;
    const ok = window.confirm(`Cancel booking #${booking.id}?`);
    if (!ok) return;
    setBusyActionId(booking.id);
    try {
      const res = await cancelVendorBooking(booking.id);
      await loadBookings();
      if (selected?.id === booking.id) {
        const detail = await fetchVendorBooking(booking.id).catch(() => null);
        setSelected(detail || null);
      }
      pushToast({
        tone: "success",
        title: "Booking updated",
        message: res?.message || `Booking #${booking.id} updated.`,
      });
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Cancel failed",
        message: err.message || "Unable to cancel booking.",
      });
    } finally {
      setBusyActionId(null);
    }
  };

  const handleRefund = async (booking) => {
    if (!booking?.id) return;
    const ok = window.confirm(`Refund booking #${booking.id}?`);
    if (!ok) return;
    setBusyActionId(booking.id);
    try {
      const res = await refundVendorBooking(booking.id);
      await loadBookings();
      if (selected?.id === booking.id) {
        const detail = await fetchVendorBooking(booking.id).catch(() => null);
        setSelected(detail || null);
      }
      pushToast({
        tone: "success",
        title: "Refund processed",
        message: res?.message || `Booking #${booking.id} refunded.`,
      });
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Refund failed",
        message: err.message || "Unable to refund booking.",
      });
    } finally {
      setBusyActionId(null);
    }
  };

  const handleDelete = async (booking) => {
    if (!booking?.id) return;
    const ok = window.confirm(`Delete booking #${booking.id}? This cannot be undone.`);
    if (!ok) return;
    setBusyActionId(booking.id);
    try {
      const res = await deleteVendorBooking(booking.id);
      await loadBookings();
      if (selected?.id === booking.id) {
        setSelected(null);
      }
      pushToast({
        tone: "success",
        title: "Booking deleted",
        message: res?.message || `Booking #${booking.id} deleted.`,
      });
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Delete failed",
        message: err.message || "Unable to delete booking.",
      });
    } finally {
      setBusyActionId(null);
    }
  };

  return (
    <div className="vendor-dashboard">
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3 mb-3">
        <div>
          <h2 className="mb-1">Manage Bookings</h2>
          <p className="text-muted mb-0">Only bookings for your cinema are shown here.</p>
        </div>
      </div>

      <section className="vendor-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3 vendor-filter-row-wrap">
          <input
            className="form-control"
            style={{ maxWidth: 340 }}
            placeholder="Search booking"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="text-muted small">
            {isLoading ? "Loading..." : `${filteredBookings.length} bookings`}
          </div>
        </div>

        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>User</th>
                <th>Movie</th>
                <th>Show Time</th>
                <th>Seats</th>
                <th>Total</th>
                <th>Status</th>
                <th>Refund</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredBookings.map((booking) => (
                <tr key={booking.id}>
                  <td>#{booking.id}</td>
                  <td>{booking.user || "-"}</td>
                  <td>{booking.movie || "-"}</td>
                  <td>{booking.showTime || "-"}</td>
                  <td>{booking.seats || "-"}</td>
                  <td>{booking.total != null ? `NPR ${Number(booking.total).toLocaleString()}` : "-"}</td>
                  <td>{booking.status || "Pending"}</td>
                  <td>{booking.refundStatus || "N/A"}</td>
                  <td>
                    <div className="vendor-actionRow" aria-label="Actions">
                      <button
                        type="button"
                        className="vendor-icon-btn"
                        onClick={() => openDetail(booking)}
                        disabled={isActionBusy(booking.id)}
                        title="View booking"
                        aria-label="View booking"
                      >
                        <Eye size={16} />
                      </button>
                      <button
                        type="button"
                        className="vendor-icon-btn"
                        onClick={() => handleRefund(booking)}
                        disabled={isActionBusy(booking.id)}
                        title="Refund booking"
                        aria-label="Refund booking"
                      >
                        <ReceiptText size={16} />
                      </button>
                      <button
                        type="button"
                        className="vendor-icon-btn"
                        onClick={() => handleCancel(booking)}
                        disabled={isActionBusy(booking.id)}
                        title="Cancel booking"
                        aria-label="Cancel booking"
                      >
                        <XCircle size={16} />
                      </button>
                      <button
                        type="button"
                        className="vendor-icon-btn"
                        onClick={() => handleDelete(booking)}
                        disabled={isActionBusy(booking.id)}
                        title="Delete booking"
                        aria-label="Delete booking"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!isLoading && filteredBookings.length === 0 ? (
                <tr>
                  <td colSpan="9">No bookings found.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {selected ? (
        <section className="vendor-card mt-3">
          <div className="vendor-card-header">
            <div>
              <h3>Booking #{selected.id}</h3>
              <p>Read-only booking details for this vendor.</p>
            </div>
          </div>
          <div className="row g-2">
            <div className="col-md-4"><strong>User:</strong> {selected.user || "-"}</div>
            <div className="col-md-4"><strong>User Email:</strong> {selected.userEmail || "-"}</div>
            <div className="col-md-4"><strong>Movie:</strong> {selected.movie || "-"}</div>
            <div className="col-md-4"><strong>Show Time:</strong> {selected.showTime || "-"}</div>
            <div className="col-md-4"><strong>Seats:</strong> {selected.seats || "-"}</div>
            <div className="col-md-4"><strong>Status:</strong> {selected.status || "Pending"}</div>
            <div className="col-md-4">
              <strong>Total:</strong>{" "}
              {selected.total != null ? `NPR ${Number(selected.total).toLocaleString()}` : "-"}
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
