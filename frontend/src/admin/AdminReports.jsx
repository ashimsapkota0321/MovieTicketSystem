import { Download, Filter } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import { reportHighlights, movies, vendors } from "./data";

export default function AdminReports() {
  return (
    <>
      <AdminPageHeader
        title="Reports & Analytics"
        subtitle="Revenue, booking trends, and performance insights."
      >
        <button type="button" className="btn btn-outline-light admin-btn">
          <Download size={16} className="me-2" />
          Export PDF
        </button>
        <button type="button" className="btn btn-outline-light admin-btn">
          <Download size={16} className="me-2" />
          Export CSV
        </button>
      </AdminPageHeader>

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div className="d-flex gap-2 flex-wrap">
            <input type="date" className="form-control" defaultValue="2026-02-01" />
            <input type="date" className="form-control" defaultValue="2026-02-15" />
            <select className="form-select">
              <option>Vendor</option>
              {vendors.map((vendor) => (
                <option key={vendor.id}>{vendor.name}</option>
              ))}
            </select>
            <select className="form-select">
              <option>Movie</option>
              {movies.map((movie) => (
                <option key={movie.id}>{movie.title}</option>
              ))}
            </select>
          </div>
          <button type="button" className="btn btn-primary admin-btn">
            <Filter size={16} className="me-2" />
            Apply Filters
          </button>
        </div>

        <div className="admin-grid-3">
          <div className="admin-card">
            <div className="admin-kpi">
              <strong>Rs {reportHighlights.revenue.toLocaleString()}</strong>
              <small>Total Revenue</small>
            </div>
          </div>
          <div className="admin-card">
            <div className="admin-kpi">
              <strong>{reportHighlights.bookings}</strong>
              <small>Total Bookings</small>
            </div>
          </div>
          <div className="admin-card">
            <div className="admin-kpi">
              <strong>{reportHighlights.cancellationRate}%</strong>
              <small>Cancellation Rate</small>
            </div>
          </div>
        </div>
      </section>

      <section className="admin-grid-2">
        <div className="admin-card">
          <div className="admin-card-header">
            <div>
              <h5 className="mb-1">Top Movies</h5>
              <small className="text-muted">Highest revenue in selected range</small>
            </div>
          </div>
          <div className="table-responsive">
            <table className="table admin-table">
              <thead>
                <tr>
                  <th>Movie</th>
                  <th>Revenue</th>
                  <th>Bookings</th>
                </tr>
              </thead>
              <tbody>
                {reportHighlights.topMovies.map((movie) => (
                  <tr key={movie.title}>
                    <td className="fw-semibold">{movie.title}</td>
                    <td>Rs {movie.revenue.toLocaleString()}</td>
                    <td>{movie.bookings}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="admin-card">
          <div className="admin-card-header">
            <div>
              <h5 className="mb-1">Top Vendors</h5>
              <small className="text-muted">Best performing partners</small>
            </div>
          </div>
          <div className="table-responsive">
            <table className="table admin-table">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>Revenue</th>
                  <th>Bookings</th>
                </tr>
              </thead>
              <tbody>
                {reportHighlights.topVendors.map((vendor) => (
                  <tr key={vendor.name}>
                    <td className="fw-semibold">{vendor.name}</td>
                    <td>Rs {vendor.revenue.toLocaleString()}</td>
                    <td>{vendor.bookings}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </>
  );
}
