import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Eye, ReceiptText, Trash2, XCircle } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import AdminPageHeader from "./components/AdminPageHeader";
import AdminModal from "./components/AdminModal";
import ConfirmModal from "./components/ConfirmModal";
import { useAdminToast } from "./AdminToastContext";
import {
  cancelAdminBooking,
  deleteAdminBooking,
  fetchAdminBooking,
  fetchAdminBookings,
  markAdminBookingComplete,
  refundAdminBooking,
} from "../lib/catalogApi";

export default function AdminBookings() {
  const PAGE_SIZE = 8;
  const { pushToast } = useAdminToast();
  const [showConfirm, setShowConfirm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showView, setShowView] = useState(false);
  const [bookings, setBookings] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [activeBooking, setActiveBooking] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("Status");
  const [dateFilter, setDateFilter] = useState("");
  const [searchParams] = useSearchParams();
  const queryFromUrl = String(searchParams.get("q") || "");

  useEffect(() => {
    setSearchTerm(queryFromUrl);
  }, [queryFromUrl]);

  const filteredBookings = useMemo(() => {
    let list = [...bookings];

    if (searchTerm.trim()) {
      const term = searchTerm.trim().toLowerCase();
      list = list.filter((booking) => {
        const haystack = [
          booking.id,
          booking.user,
          booking.movie,
          booking.showTime,
          booking.seats,
          booking.status,
          booking.refundStatus,
          booking.total,
        ]
          .map((value) => String(value || "").toLowerCase())
          .join(" ");
        return haystack.includes(term);
      });
    }

    if (statusFilter !== "Status") {
      list = list.filter((booking) => resolveAdminBookingStatus(booking).label === statusFilter);
    }

    if (dateFilter) {
      list = list.filter((booking) => {
        const rawDate = booking.bookingDate || booking.date || booking.createdAt || booking.created_at;
        if (!rawDate) return false;
        const isoDate = new Date(rawDate);
        if (Number.isNaN(isoDate.getTime())) return false;
        return isoDate.toISOString().slice(0, 10) === dateFilter;
      });
    }

    return list;
  }, [bookings, searchTerm, statusFilter, dateFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredBookings.length / PAGE_SIZE));
  const paginatedBookings = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filteredBookings.slice(start, start + PAGE_SIZE);
  }, [filteredBookings, currentPage]);

  useEffect(() => {
    setCurrentPage((prev) => Math.min(prev, totalPages));
  }, [totalPages]);

  const loadBookings = async () => {
    setIsLoading(true);
    try {
      const list = await fetchAdminBookings();
      setBookings(Array.isArray(list) ? list : []);
    } catch (error) {
      pushToast({
        title: "Bookings unavailable",
        message: error.message || "Unable to load bookings.",
      });
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadBookings();
  }, []);

  const openView = async (booking) => {
    if (!booking?.id) return;
    try {
      const detail = await fetchAdminBooking(booking.id);
      setActiveBooking(detail || booking);
      setShowView(true);
    } catch (error) {
      pushToast({
        title: "Booking unavailable",
        message: error.message || "Unable to load booking details.",
      });
    }
  };

  const confirmCancel = (booking) => {
    setActiveBooking(booking);
    setShowConfirm(true);
  };

  const confirmDelete = (booking) => {
    setActiveBooking(booking);
    setShowDeleteConfirm(true);
  };

  const handleCancel = async () => {
    if (!activeBooking?.id) return;
    try {
      await cancelAdminBooking(activeBooking.id);
      await loadBookings();
      setShowConfirm(false);
      pushToast({ title: "Booking cancelled", message: "Refund status updated." });
    } catch (error) {
      pushToast({
        title: "Cancel failed",
        message: error.message || "Unable to cancel booking.",
      });
    }
  };

  const handleRefund = async (booking) => {
    if (!booking?.id) return;
    try {
      await refundAdminBooking(booking.id);
      await loadBookings();
      pushToast({ title: "Booking refunded", message: "Refund processed." });
    } catch (error) {
      pushToast({
        title: "Refund failed",
        message: error.message || "Unable to refund booking.",
      });
    }
  };

  const handleMarkComplete = async (booking) => {
    if (!booking?.id) return;
    if (!isBookingPendingStatus(booking)) {
      const statusValue = String(booking?.status || "").trim().toUpperCase();
      const isPaidLike =
        statusValue === "PAID" ||
        statusValue === "CONFIRMED" ||
        statusValue === "SUCCESS";
      pushToast({
        title: isPaidLike ? "Already paid" : "Status locked",
        message: isPaidLike
          ? "This booking is already paid/confirmed. Status change is not allowed."
          : "Only pending bookings can be marked complete.",
      });
      return;
    }
    try {
      await markAdminBookingComplete(booking.id);
      await loadBookings();
      pushToast({ title: "Booking completed", message: `Booking #${booking.id} marked complete.` });
    } catch (error) {
      pushToast({
        title: "Status update failed",
        message: error.message || "Unable to mark booking complete.",
      });
    }
  };

  const handleDelete = async () => {
    if (!activeBooking?.id) return;
    try {
      await deleteAdminBooking(activeBooking.id);
      await loadBookings();
      setShowDeleteConfirm(false);
      pushToast({ title: "Booking deleted", message: "Booking removed." });
    } catch (error) {
      pushToast({
        title: "Delete failed",
        message: error.message || "Unable to delete booking.",
      });
    }
  };

  return (
    <>
      <AdminPageHeader
        title="Manage Bookings"
        subtitle="Track payments, cancellations, and refund status."
      />

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div className="d-flex gap-2 flex-wrap admin-filter-row">
            <input
              className="form-control"
              placeholder="Search booking ID"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
            />
            <select
              className="form-select"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option>Status</option>
              <option>Paid</option>
              <option>Pending</option>
              <option>Cancelled</option>
              <option>Refunded</option>
            </select>
            <input
              type="date"
              className="form-control"
              value={dateFilter}
              onChange={(event) => setDateFilter(event.target.value)}
            />
          </div>
          <div className="text-muted small">
            {isLoading ? "Loading bookings..." : `${filteredBookings.length} bookings`}
          </div>
        </div>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Booking ID</th>
                <th>User</th>
                <th>Movie</th>
                <th>Show Time</th>
                <th>Seats</th>
                <th>Total</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {paginatedBookings.map((booking) => {
                const mergedStatus = resolveAdminBookingStatus(booking);
                return (
                  <tr key={booking.id}>
                    <td>{booking.id}</td>
                    <td>{booking.user}</td>
                    <td>{booking.movie}</td>
                    <td>{booking.showTime}</td>
                    <td>{booking.seats || "-"}</td>
                    <td>Rs {typeof booking.total === "number" ? booking.total.toLocaleString() : booking.total || 0}</td>
                    <td>
                      <span className={`badge-soft ${mergedStatus.tone}`}>{mergedStatus.label}</span>
                    </td>
                    <td>
                      <div className="d-flex gap-2">
                        <button
                          type="button"
                          className="btn btn-outline-light btn-sm"
                          onClick={() => handleMarkComplete(booking)}
                          title={isBookingPendingStatus(booking) ? "Mark complete" : "Status change not allowed"}
                          aria-label="Mark complete"
                        >
                          <CheckCircle2 size={16} />
                        </button>
                        <button
                          type="button"
                          className="btn btn-outline-light btn-sm"
                          onClick={() => openView(booking)}
                        >
                          <Eye size={16} />
                        </button>
                        <button
                          type="button"
                          className="btn btn-outline-light btn-sm"
                          onClick={() => handleRefund(booking)}
                        >
                          <ReceiptText size={16} />
                        </button>
                        <button
                          type="button"
                          className="btn btn-outline-light btn-sm"
                          onClick={() => confirmCancel(booking)}
                        >
                          <XCircle size={16} />
                        </button>
                        <button
                          type="button"
                          className="btn btn-outline-light btn-sm"
                          onClick={() => confirmDelete(booking)}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {!isLoading && filteredBookings.length === 0 ? (
                <tr>
                  <td colSpan="8">No bookings yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <nav className="d-flex justify-content-between align-items-center mt-3">
          <span className="text-muted small">Page {currentPage} of {totalPages}</span>
          <ul className="pagination mb-0">
            <li className={`page-item ${currentPage === 1 ? "disabled" : ""}`}>
              <button
                type="button"
                className="page-link"
                onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                disabled={currentPage === 1}
              >
                Prev
              </button>
            </li>
            {Array.from({ length: totalPages }, (_, idx) => idx + 1).map((page) => (
              <li key={page} className={`page-item ${currentPage === page ? "active" : ""}`}>
                <button
                  type="button"
                  className="page-link"
                  onClick={() => setCurrentPage(page)}
                >
                  {page}
                </button>
              </li>
            ))}
            <li className={`page-item ${currentPage === totalPages ? "disabled" : ""}`}>
              <button
                type="button"
                className="page-link"
                onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                disabled={currentPage === totalPages}
              >
                Next
              </button>
            </li>
          </ul>
        </nav>
      </section>

      <ConfirmModal
        show={showConfirm}
        title="Cancel booking?"
        description="Cancellation will trigger refund workflow for paid bookings."
        onCancel={() => setShowConfirm(false)}
        onConfirm={handleCancel}
      />

      <ConfirmModal
        show={showDeleteConfirm}
        title="Delete booking?"
        description="This will remove the booking permanently."
        onCancel={() => setShowDeleteConfirm(false)}
        onConfirm={handleDelete}
      />

      <AdminModal
        show={showView}
        title="Booking Details"
        onClose={() => setShowView(false)}
      >
        {activeBooking ? (
          <div className="admin-details-view">
            <div className="admin-details-row">
              <div className="admin-details-label">Booking ID</div>
              <div className="admin-details-value">{activeBooking.id}</div>
            </div>
            <div className="admin-details-row">
              <div className="admin-details-label">User</div>
              <div className="admin-details-value">{activeBooking.user}</div>
            </div>
            {activeBooking.userEmail ? (
              <div className="admin-details-row">
                <div className="admin-details-label">Email</div>
                <div className="admin-details-value">{activeBooking.userEmail}</div>
              </div>
            ) : null}
            <div className="admin-details-row">
              <div className="admin-details-label">Movie</div>
              <div className="admin-details-value">{activeBooking.movie || "-"}</div>
            </div>
            <div className="admin-details-row">
              <div className="admin-details-label">Cinema</div>
              <div className="admin-details-value">{activeBooking.vendor || "-"}</div>
            </div>
            <div className="admin-details-row">
              <div className="admin-details-label">Show Time</div>
              <div className="admin-details-value">{activeBooking.showTime || "-"}</div>
            </div>
            <div className="admin-details-row">
              <div className="admin-details-label">Seats</div>
              <div className="admin-details-value">{activeBooking.seats || "-"}</div>
            </div>
            <div className="admin-details-row">
              <div className="admin-details-label">Total</div>
              <div className="admin-details-value">Rs {activeBooking.total || 0}</div>
            </div>
            <div className="admin-details-row">
              <div className="admin-details-label">Status</div>
              <div className="admin-details-value">{activeBooking.status}</div>
            </div>
            {Array.isArray(activeBooking.payments) && activeBooking.payments.length ? (
              <div className="admin-details-section">
                <h4 className="admin-details-title">Payments</h4>
                {activeBooking.payments.map((payment) => (
                  <div key={payment.id}>
                    <div className="admin-details-row">
                      <div className="admin-details-label">Method</div>
                      <div className="admin-details-value">{payment.method}</div>
                    </div>
                    <div className="admin-details-row">
                      <div className="admin-details-label">Status</div>
                      <div className="admin-details-value">{payment.status}</div>
                    </div>
                    <div className="admin-details-row">
                      <div className="admin-details-label">Amount</div>
                      <div className="admin-details-value">Rs {payment.amount}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : (
          <div>No booking selected.</div>
        )}
      </AdminModal>
    </>
  );
}

function resolveAdminBookingStatus(booking) {
  const bookingStatus = String(booking?.status || "").trim().toUpperCase();
  const refundStatus = String(booking?.refundStatus || booking?.refund_status || "").trim().toUpperCase();

  if (refundStatus === "REFUNDED" || refundStatus === "COMPLETED") {
    return { label: "Refunded", tone: "info" };
  }
  if (refundStatus === "PENDING") {
    return { label: "Refund Pending", tone: "warning" };
  }
  if (bookingStatus === "PAID" || bookingStatus === "SUCCESS" || bookingStatus === "CONFIRMED") {
    return { label: "Paid", tone: "success" };
  }
  if (bookingStatus === "PENDING") {
    return { label: "Pending", tone: "warning" };
  }
  if (bookingStatus === "CANCELLED" || bookingStatus === "FAILED") {
    return { label: "Cancelled", tone: "danger" };
  }

  return { label: booking?.status || "Unknown", tone: "info" };
}

function isBookingPendingStatus(booking) {
  const statusValue = String(booking?.status || "").trim().toUpperCase();
  return statusValue === "PENDING";
}
