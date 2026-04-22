import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Check, CheckCircle2, Eye, ReceiptText, Trash2, XCircle } from "lucide-react";
import Pagination from "../components/Pagination";
import ConfirmModal from "../admin/components/ConfirmModal";
import {
  cancelVendorBooking,
  deleteVendorBooking,
  fetchVendorBooking,
  fetchVendorBookings,
  markVendorBookingComplete,
  refundVendorBooking,
} from "../lib/catalogApi";
import { useVendorToast } from "./VendorToastContext";

export default function VendorBookings() {
  const BOOKINGS_PER_PAGE = 10;
  const [bookings, setBookings] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [query, setQuery] = useState("");
  const [busyActionId, setBusyActionId] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [showConfirm, setShowConfirm] = useState(false);
  const [confirmAction, setConfirmAction] = useState(null);
  const [confirmBooking, setConfirmBooking] = useState(null);
  const [confirmTitle, setConfirmTitle] = useState("");
  const [confirmDescription, setConfirmDescription] = useState("");
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

  const totalPages = Math.max(1, Math.ceil(filteredBookings.length / BOOKINGS_PER_PAGE));

  const paginatedBookings = useMemo(() => {
    const start = (currentPage - 1) * BOOKINGS_PER_PAGE;
    return filteredBookings.slice(start, start + BOOKINGS_PER_PAGE);
  }, [filteredBookings, currentPage]);

  useEffect(() => {
    setCurrentPage(1);
  }, [query]);

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const openDetail = async (booking) => {
    if (!booking?.id) return;
    setSelected(booking);
    try {
      const detail = await fetchVendorBooking(booking.id);
      setSelected(detail || booking);
    } catch {
      setSelected(booking);
    }
  };

  const isActionBusy = (bookingId) => busyActionId === bookingId;

  const performApproveCancellation = async (booking) => {
    if (!booking?.id) return;
    if (!hasPendingCancellationRequest(booking)) {
      pushToast({
        tone: "info",
        title: "No pending request",
        message: "Customer cancellation request is not pending for this booking.",
      });
      return;
    }
    setBusyActionId(booking.id);
    try {
      const res = await cancelVendorBooking(booking.id, { action: "APPROVE" });
      await loadBookings();
      if (selected?.id === booking.id) {
        const detail = await fetchVendorBooking(booking.id).catch(() => null);
        setSelected(detail || null);
      }
      pushToast({
        tone: "success",
        title: "Cancellation approved",
        message: res?.message || `Cancellation request for booking #${booking.id} approved.`,
      });
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Approval failed",
        message: err.message || "Unable to approve cancellation request.",
      });
    } finally {
      setBusyActionId(null);
    }
  };

  const performRejectCancellation = async (booking) => {
    if (!booking?.id) return;
    if (!hasPendingCancellationRequest(booking)) {
      pushToast({
        tone: "info",
        title: "No pending request",
        message: "Customer cancellation request is not pending for this booking.",
      });
      return;
    }
    setBusyActionId(booking.id);
    try {
      const res = await cancelVendorBooking(booking.id, { action: "REJECT" });
      await loadBookings();
      if (selected?.id === booking.id) {
        const detail = await fetchVendorBooking(booking.id).catch(() => null);
        setSelected(detail || null);
      }
      pushToast({
        tone: "success",
        title: "Cancellation rejected",
        message: res?.message || `Cancellation request for booking #${booking.id} rejected.`,
      });
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Rejection failed",
        message: err.message || "Unable to reject cancellation request.",
      });
    } finally {
      setBusyActionId(null);
    }
  };

  const performRefund = async (booking) => {
    if (!booking?.id) return;
    if (!canRefundVendorBooking(booking)) {
      pushToast({
        tone: "info",
        title: "Refund not available",
        message: "Refund can be processed only for paid/confirmed bookings.",
      });
      return;
    }
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

  const performDelete = async (booking) => {
    if (!booking?.id) return;
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

  const performMarkComplete = async (booking) => {
    if (!booking?.id) return;
    if (!isVendorBookingPending(booking)) {
      pushToast({
        tone: "info",
        title: "Status locked",
        message: "Only pending bookings can be marked complete.",
      });
      return;
    }

    setBusyActionId(booking.id);
    try {
      const res = await markVendorBookingComplete(booking.id);
      await loadBookings();
      if (selected?.id === booking.id) {
        const detail = await fetchVendorBooking(booking.id).catch(() => null);
        setSelected(detail || null);
      }
      pushToast({
        tone: "success",
        title: "Booking completed",
        message: res?.message || `Booking #${booking.id} marked complete.`,
      });
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Status update failed",
        message: err.message || "Unable to mark booking complete.",
      });
    } finally {
      setBusyActionId(null);
    }
  };

  const openConfirm = (action, booking) => {
    if (!booking?.id) return;
    if (action === "complete" && !isVendorBookingPending(booking)) {
      const statusValue = String(booking?.status || "").trim().toUpperCase();
      const isPaidLike =
        statusValue === "PAID" ||
        statusValue === "CONFIRMED" ||
        statusValue === "SUCCESS";
      pushToast({
        tone: "info",
        title: isPaidLike ? "Already paid" : "Status locked",
        message: isPaidLike
          ? "This booking is already paid/confirmed. Status change is not allowed."
          : "Only pending bookings can be marked complete.",
      });
      return;
    }
    if (action === "refund" && !canRefundVendorBooking(booking)) {
      pushToast({
        tone: "info",
        title: "Refund not available",
        message: "Refund can be processed only for paid/confirmed bookings.",
      });
      return;
    }
    if ((action === "cancelApprove" || action === "cancelReject") && !hasPendingCancellationRequest(booking)) {
      pushToast({
        tone: "info",
        title: "No pending request",
        message: "Customer cancellation request is not pending for this booking.",
      });
      return;
    }

    setConfirmBooking(booking);
    setConfirmAction(action);
    if (action === "complete") {
      setConfirmTitle("Mark booking complete?");
      setConfirmDescription(`Booking #${booking.id} will be marked complete and cannot be moved backward.`);
    } else if (action === "refund") {
      setConfirmTitle("Refund booking?");
      setConfirmDescription(`A refund will be processed for booking #${booking.id}.`);
    } else if (action === "cancelApprove") {
      setConfirmTitle("Approve cancellation request?");
      setConfirmDescription(`Are you sure you want to approve cancellation for booking #${booking.id}? Refund rules will be applied.`);
    } else if (action === "cancelReject") {
      setConfirmTitle("Reject cancellation request?");
      setConfirmDescription(`Are you sure you want to reject cancellation request for booking #${booking.id}?`);
    } else {
      setConfirmTitle("Delete booking?");
      setConfirmDescription(`Booking #${booking.id} will be permanently deleted. This cannot be undone.`);
    }
    setShowConfirm(true);
  };

  const closeConfirm = () => {
    if (busyActionId != null) return;
    setShowConfirm(false);
    setConfirmAction(null);
    setConfirmBooking(null);
    setConfirmTitle("");
    setConfirmDescription("");
  };

  const handleConfirm = async () => {
    if (!confirmBooking?.id || !confirmAction) return;
    if (confirmAction === "complete") {
      await performMarkComplete(confirmBooking);
    } else if (confirmAction === "refund") {
      await performRefund(confirmBooking);
    } else if (confirmAction === "cancelApprove") {
      await performApproveCancellation(confirmBooking);
    } else if (confirmAction === "cancelReject") {
      await performRejectCancellation(confirmBooking);
    } else if (confirmAction === "delete") {
      await performDelete(confirmBooking);
    }
    setShowConfirm(false);
    setConfirmAction(null);
    setConfirmBooking(null);
    setConfirmTitle("");
    setConfirmDescription("");
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
              {paginatedBookings.map((booking) => (
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
                        onClick={() => openConfirm("complete", booking)}
                        disabled={isActionBusy(booking.id)}
                        title={isVendorBookingPending(booking) ? "Mark complete" : "Status change not allowed"}
                        aria-label="Mark complete"
                      >
                        <CheckCircle2 size={16} />
                      </button>
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
                        onClick={() => openConfirm("refund", booking)}
                        disabled={isActionBusy(booking.id) || !canRefundVendorBooking(booking)}
                        title={canRefundVendorBooking(booking) ? "Refund booking" : "Refund not available for current status"}
                        aria-label="Refund booking"
                      >
                        <ReceiptText size={16} />
                      </button>
                      <button
                        type="button"
                        className="vendor-icon-btn"
                        onClick={() => openConfirm("cancelApprove", booking)}
                        disabled={isActionBusy(booking.id) || !hasPendingCancellationRequest(booking)}
                        title={hasPendingCancellationRequest(booking) ? "Approve customer cancellation request" : "No pending customer cancellation request"}
                        aria-label="Approve cancellation request"
                      >
                        <Check size={16} />
                      </button>
                      <button
                        type="button"
                        className="vendor-icon-btn"
                        onClick={() => openConfirm("cancelReject", booking)}
                        disabled={isActionBusy(booking.id) || !hasPendingCancellationRequest(booking)}
                        title={hasPendingCancellationRequest(booking) ? "Reject customer cancellation request" : "No pending customer cancellation request"}
                        aria-label="Reject cancellation request"
                      >
                        <XCircle size={16} />
                      </button>
                      <button
                        type="button"
                        className="vendor-icon-btn"
                        onClick={() => openConfirm("delete", booking)}
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
        {filteredBookings.length > 0 ? (
          <div className="d-flex flex-wrap justify-content-between align-items-center mt-3 gap-2">
            <small className="text-muted">
              Showing {(currentPage - 1) * BOOKINGS_PER_PAGE + 1}-
              {Math.min(currentPage * BOOKINGS_PER_PAGE, filteredBookings.length)} of {filteredBookings.length}
            </small>
            <Pagination page={currentPage} totalPages={totalPages} onPageChange={setCurrentPage} />
          </div>
        ) : null}
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

      <ConfirmModal
        show={showConfirm}
        title={confirmTitle}
        description={confirmDescription}
        onCancel={closeConfirm}
        onConfirm={handleConfirm}
      />
    </div>
  );
}

function isVendorBookingPending(booking) {
  const statusValue = String(booking?.status || "").trim().toUpperCase();
  return statusValue === "PENDING";
}

function hasPendingCancellationRequest(booking) {
  const requestStatus = String(booking?.cancellation?.request_status || "").trim().toUpperCase();
  return requestStatus === "PENDING";
}

function canRefundVendorBooking(booking) {
  const bookingStatus = String(booking?.status || "").trim().toUpperCase();
  const refundStatus = String(booking?.refundStatus || booking?.refund_status || "").trim().toUpperCase();
  if (refundStatus === "REFUNDED" || refundStatus === "COMPLETED") {
    return false;
  }
  return bookingStatus === "PAID" || bookingStatus === "CONFIRMED";
}
