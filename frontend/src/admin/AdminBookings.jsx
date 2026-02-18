import { useState } from "react";
import { Eye, ReceiptText, XCircle } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import ConfirmModal from "./components/ConfirmModal";
import { bookings } from "./data";
import { useAdminToast } from "./AdminToastContext";

export default function AdminBookings() {
  const { pushToast } = useAdminToast();
  const [showConfirm, setShowConfirm] = useState(false);

  return (
    <>
      <AdminPageHeader
        title="Manage Bookings"
        subtitle="Track payments, cancellations, and refund status."
      />

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div className="d-flex gap-2 flex-wrap">
            <input className="form-control" placeholder="Search booking ID" />
            <select className="form-select">
              <option>Status</option>
              <option>Paid</option>
              <option>Pending</option>
              <option>Cancelled</option>
              <option>Refunded</option>
            </select>
            <input type="date" className="form-control" defaultValue="2026-02-15" />
          </div>
          <div className="text-muted small">{bookings.length} bookings</div>
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
                <th>Refund</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {bookings.map((booking) => (
                <tr key={booking.id}>
                  <td>{booking.id}</td>
                  <td>{booking.user}</td>
                  <td>{booking.movie}</td>
                  <td>{booking.showTime}</td>
                  <td>{booking.seats}</td>
                  <td>Rs {booking.total}</td>
                  <td>
                    <span
                      className={`badge-soft ${{
                        Paid: "success",
                        Pending: "warning",
                        Cancelled: "danger",
                        Refunded: "info",
                      }[booking.status] || "info"}`}
                    >
                      {booking.status}
                    </span>
                  </td>
                  <td>
                    <span className={`badge-soft ${booking.status === "Refunded" ? "info" : "warning"}`}>
                      {booking.status === "Refunded" ? "Refunded" : "N/A"}
                    </span>
                  </td>
                  <td>
                    <div className="d-flex gap-2">
                      <button type="button" className="btn btn-outline-light btn-sm">
                        <Eye size={16} />
                      </button>
                      <button type="button" className="btn btn-outline-light btn-sm">
                        <ReceiptText size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => setShowConfirm(true)}
                      >
                        <XCircle size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <nav className="d-flex justify-content-between align-items-center mt-3">
          <span className="text-muted small">Page 1 of 5</span>
          <ul className="pagination mb-0">
            <li className="page-item disabled"><span className="page-link">Prev</span></li>
            <li className="page-item active"><span className="page-link">1</span></li>
            <li className="page-item"><span className="page-link">2</span></li>
            <li className="page-item"><span className="page-link">3</span></li>
            <li className="page-item"><span className="page-link">Next</span></li>
          </ul>
        </nav>
      </section>

      <ConfirmModal
        show={showConfirm}
        title="Cancel booking?"
        description="Cancellation will trigger refund workflow for paid bookings."
        onCancel={() => setShowConfirm(false)}
        onConfirm={() => {
          setShowConfirm(false);
          pushToast({ title: "Booking cancelled", message: "Refund status updated." });
        }}
      />
    </>
  );
}
