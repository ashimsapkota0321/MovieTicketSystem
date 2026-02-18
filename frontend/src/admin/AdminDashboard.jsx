import {
  CalendarCheck,
  Film,
  Users,
  Ticket,
  DollarSign,
  Plus,
  FileText,
  Building2,
  Sparkles,
} from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import { bookings, movies, users, vendors, shows } from "./data";
import { useAdminToast } from "./AdminToastContext";

const statConfig = [
  { label: "Total Movies", value: movies.length, icon: Film, tone: "" },
  { label: "Vendors", value: vendors.length, icon: Building2, tone: "stat-success" },
  { label: "Users", value: users.length, icon: Users, tone: "" },
  { label: "Bookings", value: bookings.length, icon: Ticket, tone: "stat-warning" },
  {
    label: "Shows Today",
    value: shows.filter((show) => show.date === "2026-02-15").length,
    icon: CalendarCheck,
    tone: "stat-danger",
  },
  {
    label: "Revenue",
    value: `Rs ${bookings.reduce((total, item) => total + item.total, 0).toLocaleString()}`,
    icon: DollarSign,
    tone: "stat-success",
  },
];

const recentBookings = bookings.slice(0, 10);

export default function AdminDashboard() {
  const { pushToast } = useAdminToast();

  return (
    <>
      <AdminPageHeader
        title="Admin Dashboard"
        subtitle="Overview of the MeroTicket system performance and activities."
      >
        <button
          type="button"
          className="btn btn-primary admin-btn"
          onClick={() =>
            pushToast({
              title: "Quick action",
              message: "Opening add movie form.",
            })
          }
        >
          <Plus size={16} className="me-2" />
          Add Movie
        </button>
        <button type="button" className="btn btn-outline-light admin-btn">
          <FileText size={16} className="me-2" />
          View Reports
        </button>
      </AdminPageHeader>

      <section className="admin-grid-3">
        {statConfig.map((stat) => {
          const Icon = stat.icon;
          return (
            <div key={stat.label} className={`admin-stat ${stat.tone}`}>
              <div className="stat-icon">
                <Icon size={20} />
              </div>
              <div className="stat-value">{stat.value}</div>
              <div className="stat-meta">
                <span>{stat.label}</span>
                <Sparkles size={14} />
                <span className="text-success">+8%</span>
              </div>
              <div className="sparkline">
                {[12, 18, 10, 22, 16, 26, 20].map((height, index) => (
                  <span key={index} style={{ height }} />
                ))}
              </div>
            </div>
          );
        })}
      </section>

      <section className="admin-grid-2">
        <div className="admin-card">
          <div className="admin-card-header">
            <div>
              <h5 className="mb-1">Revenue Analytics</h5>
              <small className="text-muted">Weekly performance snapshot</small>
            </div>
            <button type="button" className="btn btn-sm btn-outline-light">
              Export
            </button>
          </div>
          <div className="admin-chart">
            <svg width="100%" height="100%" viewBox="0 0 420 180" preserveAspectRatio="none">
              <polyline
                points="0,120 60,98 120,110 180,70 240,90 300,50 360,60 420,35"
                fill="none"
                stroke="#6d8bff"
                strokeWidth="3"
              />
              <polyline
                points="0,140 60,130 120,100 180,95 240,70 300,85 360,72 420,66"
                fill="none"
                stroke="#22d3ee"
                strokeWidth="2"
                opacity="0.7"
              />
            </svg>
          </div>
        </div>

        <div className="admin-card">
          <div className="admin-card-header">
            <div>
              <h5 className="mb-1">System Health</h5>
              <small className="text-muted">Server status and SLA</small>
            </div>
            <span className="badge-soft success">Stable</span>
          </div>
          <div className="admin-grid-2">
            <div className="admin-kpi">
              <strong>99.8%</strong>
              <small>Uptime</small>
            </div>
            <div className="admin-kpi">
              <strong>185 ms</strong>
              <small>Avg response</small>
            </div>
            <div className="admin-kpi">
              <strong>14</strong>
              <small>Incidents</small>
            </div>
            <div className="admin-kpi">
              <strong>2 min</strong>
              <small>Recovery</small>
            </div>
          </div>
          <div className="mt-4">
            <button type="button" className="btn btn-primary admin-btn w-100">
              Download Overall Report
            </button>
          </div>
        </div>
      </section>

      <section className="admin-card">
        <div className="admin-card-header">
          <div>
            <h5 className="mb-1">Recent Bookings</h5>
            <small className="text-muted">Latest 10 confirmed transactions</small>
          </div>
          <div className="d-flex gap-2">
            <button type="button" className="btn btn-outline-light btn-sm">
              View All
            </button>
            <button type="button" className="btn btn-primary btn-sm">
              View Reports
            </button>
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
              </tr>
            </thead>
            <tbody>
              {recentBookings.map((booking) => (
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="admin-card">
        <div className="admin-card-header">
          <div>
            <h5 className="mb-1">Quick Actions</h5>
            <small className="text-muted">Speed up daily operations</small>
          </div>
        </div>
        <div className="d-flex flex-wrap gap-3">
          {[
            { label: "Add Movie", icon: Film },
            { label: "Add Vendor", icon: Building2 },
            { label: "Create Show", icon: CalendarCheck },
            { label: "View Reports", icon: FileText },
          ].map((action) => {
            const Icon = action.icon;
            return (
              <button
                key={action.label}
                type="button"
                className="btn btn-outline-light admin-btn"
                onClick={() =>
                  pushToast({
                    title: action.label,
                    message: "Action queued for admin review.",
                  })
                }
              >
                <Icon size={16} className="me-2" />
                {action.label}
              </button>
            );
          })}
        </div>
      </section>
    </>
  );
}
