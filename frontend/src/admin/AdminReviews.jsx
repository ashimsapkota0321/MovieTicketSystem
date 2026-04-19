import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Check, X } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import { useAdminToast } from "./AdminToastContext";
import { useAppContext } from "../context/Appcontext";
import {
  approveAdminWithdrawalRequest,
  fetchAdminBookings,
  fetchAdminWithdrawalRequests,
  rejectAdminWithdrawalRequest,
} from "../lib/catalogApi";

export default function AdminReviews() {
  const navigate = useNavigate();
  const { pushToast } = useAdminToast();
  const ctx = safeUseAppContext();
  const movies = Array.isArray(ctx?.movies) ? ctx.movies : [];

  const [withdrawals, setWithdrawals] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [loadingWithdrawals, setLoadingWithdrawals] = useState(true);
  const [loadingBookings, setLoadingBookings] = useState(true);
  const [busyWithdrawalId, setBusyWithdrawalId] = useState(null);

  const loadWithdrawals = async () => {
    setLoadingWithdrawals(true);
    try {
      const list = await fetchAdminWithdrawalRequests();
      setWithdrawals(Array.isArray(list) ? list : []);
    } catch (error) {
      pushToast({
        title: "Withdrawals unavailable",
        message: error.message || "Unable to load withdrawal requests.",
      });
      setWithdrawals([]);
    } finally {
      setLoadingWithdrawals(false);
    }
  };

  const loadBookings = async () => {
    setLoadingBookings(true);
    try {
      const list = await fetchAdminBookings();
      setBookings(Array.isArray(list) ? list : []);
    } catch (error) {
      pushToast({
        title: "Bookings unavailable",
        message: error.message || "Unable to load booking review queue.",
      });
      setBookings([]);
    } finally {
      setLoadingBookings(false);
    }
  };

  useEffect(() => {
    loadWithdrawals();
    loadBookings();
  }, []);

  const moderationItems = useMemo(() => {
    return [...movies]
      .map((movie) => ({
        ...movie,
        approvalStatus: String(movie?.approvalStatus || movie?.approval_status || "").trim().toUpperCase(),
        approvalReason: movie?.approvalReason || movie?.approval_reason || "",
      }))
      .sort((left, right) => {
        const rank = (item) => {
          if (item.approvalStatus === "PENDING") return 0;
          if (item.approvalStatus === "REJECTED") return 1;
          if (item.approvalStatus === "APPROVED") return 2;
          return 3;
        };
        return rank(left) - rank(right);
      });
  }, [movies]);

  const pendingMovies = moderationItems.filter((movie) => movie.approvalStatus === "PENDING");
  const pendingWithdrawals = withdrawals.filter((item) => String(item.status || "").trim().toUpperCase() === "PENDING");
  const riskBookings = bookings.filter((booking) => {
    const status = String(booking?.status || "").trim().toUpperCase();
    const paymentStatus = String(booking?.paymentStatus || booking?.payment_status || "").trim().toUpperCase();
    const refundStatus = String(booking?.refundStatus || booking?.refund_status || "").trim().toUpperCase();
    return status === "PENDING" || paymentStatus === "PENDING" || refundStatus === "PENDING";
  });

  const summaryCards = [
    {
      label: "Moderation queue",
      value: pendingMovies.length,
      detail: "Vendor-submitted movies waiting for a decision",
    },
    {
      label: "Withdrawal queue",
      value: pendingWithdrawals.length,
      detail: "Payout requests pending approval",
    },
    {
      label: "Risk queue",
      value: riskBookings.length,
      detail: "Bookings with payment, cancellation, or refund attention",
    },
  ];

  const handleWithdrawalDecision = async (withdrawal, decision) => {
    if (!withdrawal?.id || busyWithdrawalId === withdrawal.id) return;
    const reason = window.prompt(
      decision === "approve" ? "Reason for approval (optional)" : "Reason for rejection (optional)",
      ""
    );
    setBusyWithdrawalId(withdrawal.id);
    try {
      if (decision === "approve") {
        await approveAdminWithdrawalRequest(withdrawal.id, { note: reason || "" });
        pushToast({ title: "Withdrawal approved", message: `Request #${withdrawal.id} approved.` });
      } else {
        await rejectAdminWithdrawalRequest(withdrawal.id, { note: reason || "" });
        pushToast({ title: "Withdrawal rejected", message: `Request #${withdrawal.id} rejected.` });
      }
      await loadWithdrawals();
    } catch (error) {
      pushToast({
        title: "Decision failed",
        message: error.message || "Unable to process withdrawal decision.",
      });
    } finally {
      setBusyWithdrawalId(null);
    }
  };

  return (
    <>
      <AdminPageHeader
        title="Review Desk"
        subtitle="Moderation, payout, and risk decisions in one place."
      >
        <button type="button" className="btn btn-outline-light" onClick={() => navigate("/admin/movies")}>Go to movies</button>
      </AdminPageHeader>

      <section className="admin-card mb-4">
        <div className="row g-3">
          {summaryCards.map((item) => (
            <div className="col-12 col-md-4" key={item.label}>
              <div className="p-3 rounded-3 border border-secondary-subtle h-100">
                <div className="text-uppercase small text-muted fw-semibold">{item.label}</div>
                <div className="display-6 fw-bold">{item.value}</div>
                <div className="text-muted small">{item.detail}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="admin-card mb-4">
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
          <div>
            <h3 className="mb-1">Moderation queue</h3>
            <p className="text-muted mb-0">Vendor submissions are separated from the published catalog here.</p>
          </div>
          <span className="badge-soft warning">{pendingMovies.length} pending</span>
        </div>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Movie</th>
                <th>Flow</th>
                <th>Status</th>
                <th>Approved</th>
                <th>Reason</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {moderationItems.map((movie) => {
                const approvalStatus = movie.approvalStatus || "UNKNOWN";
                const isVendorSubmission = isVendorSubmissionMovie(movie);
                return (
                  <tr key={movie.id}>
                    <td>
                      <div className="fw-semibold">{movie.title || "Untitled movie"}</div>
                      <div className="text-muted small">{movie.approvalMetadata?.source || (isVendorSubmission ? "vendor_submission" : "published_catalog")}</div>
                    </td>
                    <td>
                      <span className={`badge-soft ${isVendorSubmission ? "warning" : "success"}`}>
                        {isVendorSubmission ? "Vendor submission" : "Published catalog"}
                      </span>
                    </td>
                    <td>
                      <span className={`badge-soft ${approvalTone(approvalStatus)}`}>{formatApprovalLabel(approvalStatus)}</span>
                    </td>
                    <td>{movie.approvedAt ? formatDate(movie.approvedAt) : "-"}</td>
                    <td className="text-muted small">{movie.approvalReason || "-"}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-outline-light admin-table-text-btn"
                        onClick={() => navigate(`/admin/movies?q=${encodeURIComponent(movie.title || "")}`)}
                      >
                        Review movie
                      </button>
                    </td>
                  </tr>
                );
              })}
              {moderationItems.length === 0 ? (
                <tr>
                  <td colSpan="6">No movies available for review.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="admin-card mb-4">
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
          <div>
            <h3 className="mb-1">Payout decisions</h3>
            <p className="text-muted mb-0">Approve or reject vendor withdrawal requests with audit metadata.</p>
          </div>
          <span className="badge-soft info">{pendingWithdrawals.length} pending</span>
        </div>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Vendor</th>
                <th>Amount</th>
                <th>Status</th>
                <th>Description</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {withdrawals.map((item) => (
                <tr key={item.id}>
                  <td>#{item.id}</td>
                  <td>{item.vendor_name || item.vendor_id || "-"}</td>
                  <td>NPR {Number(item.amount || 0).toLocaleString()}</td>
                  <td>
                    <span className={`badge-soft ${withdrawalTone(item.status)}`}>{item.status || "Unknown"}</span>
                  </td>
                  <td className="text-muted small">{item.description || "-"}</td>
                  <td>{formatDate(item.created_at)}</td>
                  <td>
                    <div className="admin-action-icon-row" aria-label="Payout actions">
                      <button
                        type="button"
                        className="btn btn-sm btn-success"
                        title="Approve"
                        aria-label="Approve"
                        disabled={busyWithdrawalId === item.id || String(item.status || "").trim().toUpperCase() !== "PENDING"}
                        onClick={() => handleWithdrawalDecision(item, "approve")}
                      >
                        <Check size={15} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-warning"
                        title="Reject"
                        aria-label="Reject"
                        disabled={busyWithdrawalId === item.id || String(item.status || "").trim().toUpperCase() !== "PENDING"}
                        onClick={() => handleWithdrawalDecision(item, "reject")}
                      >
                        <X size={15} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loadingWithdrawals && withdrawals.length === 0 ? (
                <tr>
                  <td colSpan="7">No withdrawal requests yet.</td>
                </tr>
              ) : null}
              {loadingWithdrawals ? (
                <tr>
                  <td colSpan="7">Loading withdrawal requests...</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="admin-card">
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
          <div>
            <h3 className="mb-1">Risk queue</h3>
            <p className="text-muted mb-0">Bookings with pending payments, cancellations, or refunds that need attention.</p>
          </div>
          <button type="button" className="btn btn-outline-light btn-sm" onClick={() => navigate("/admin/bookings")}>Open bookings</button>
        </div>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Booking</th>
                <th>User</th>
                <th>Movie</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {bookings.slice(0, 12).map((booking) => {
                const paymentStatus = String(booking?.paymentStatus || booking?.payment_status || "").trim() || "-";
                const refundStatus = String(booking?.refundStatus || booking?.refund_status || "").trim() || "-";
                const status = String(booking?.status || "").trim() || "-";
                const mergedStatus = resolveBookingReviewStatus({ paymentStatus, refundStatus, status });
                return (
                  <tr key={booking.id}>
                    <td>#{booking.id}</td>
                    <td>{booking.user || "-"}</td>
                    <td>{booking.movie || "-"}</td>
                    <td><span className={`badge-soft ${mergedStatus.tone}`}>{mergedStatus.label}</span></td>
                  </tr>
                );
              })}
              {!loadingBookings && bookings.length === 0 ? (
                <tr>
                  <td colSpan="4">No bookings available.</td>
                </tr>
              ) : null}
              {loadingBookings ? (
                <tr>
                  <td colSpan="4">Loading bookings...</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function safeUseAppContext() {
  try {
    return useAppContext?.();
  } catch {
    return null;
  }
}

function isVendorSubmissionMovie(movie) {
  const source = String(movie?.approvalMetadata?.source || movie?.approval_metadata?.source || "").toLowerCase();
  const status = String(movie?.approvalStatus || movie?.approval_status || "").toUpperCase();
  return source === "vendor_submission" || status === "PENDING" || status === "REJECTED";
}

function formatApprovalLabel(status) {
  if (status === "APPROVED") return "Approved";
  if (status === "REJECTED") return "Rejected";
  if (status === "PENDING") return "Pending review";
  return status || "Unknown";
}

function approvalTone(status) {
  if (status === "APPROVED") return "success";
  if (status === "REJECTED") return "danger";
  if (status === "PENDING") return "warning";
  return "info";
}

function withdrawalTone(status) {
  const value = String(status || "").trim().toUpperCase();
  if (value === "COMPLETED") return "success";
  if (value === "REJECTED") return "danger";
  if (value === "PENDING") return "warning";
  return "info";
}

function resolveBookingReviewStatus({ paymentStatus, refundStatus, status }) {
  const payment = String(paymentStatus || "").trim().toUpperCase();
  const refund = String(refundStatus || "").trim().toUpperCase();
  const booking = String(status || "").trim().toUpperCase();

  if (refund === "REFUNDED" || refund === "COMPLETED") {
    return { label: "REFUNDED", tone: "success" };
  }
  if (refund === "PENDING") {
    return { label: "REFUND PENDING", tone: "warning" };
  }
  if (refund === "FAILED") {
    return { label: "REFUND FAILED", tone: "danger" };
  }
  if (payment === "FAILED") {
    return { label: "PAYMENT FAILED", tone: "danger" };
  }
  if (payment === "PENDING") {
    return { label: "PAYMENT PENDING", tone: "warning" };
  }
  if (booking === "CANCELLED") {
    return { label: "CANCELLED", tone: "danger" };
  }
  if (booking === "CONFIRMED" || booking === "PAID" || payment === "SUCCESS" || payment === "PAID") {
    return { label: "PAID", tone: "success" };
  }

  return { label: booking || "UNKNOWN", tone: "info" };
}

function formatDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}
