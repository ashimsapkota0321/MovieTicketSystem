import { useEffect, useMemo, useState } from "react";
import { Download, Filter } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import { useAdminToast } from "./AdminToastContext";
import {
  fetchAdminBookings,
  fetchMovies,
  fetchVendorsAdmin,
} from "../lib/catalogApi";

export default function AdminReports() {
  const { pushToast } = useAdminToast();
  const [bookings, setBookings] = useState([]);
  const [movies, setMovies] = useState([]);
  const [vendors, setVendors] = useState([]);
  const [loading, setLoading] = useState(true);

  const [draftStartDate, setDraftStartDate] = useState("");
  const [draftEndDate, setDraftEndDate] = useState("");
  const [draftVendor, setDraftVendor] = useState("");
  const [draftMovie, setDraftMovie] = useState("");

  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selectedVendor, setSelectedVendor] = useState("");
  const [selectedMovie, setSelectedMovie] = useState("");

  useEffect(() => {
    let active = true;

    const loadData = async () => {
      try {
        setLoading(true);
        const [bookingList, movieList, vendorList] = await Promise.all([
          fetchAdminBookings().catch(() => []),
          fetchMovies().catch(() => []),
          fetchVendorsAdmin().catch(() => []),
        ]);

        if (!active) return;
        setBookings(Array.isArray(bookingList) ? bookingList : []);
        setMovies(Array.isArray(movieList) ? movieList : []);
        setVendors(Array.isArray(vendorList) ? vendorList : []);
      } catch (error) {
        if (!active) return;
        pushToast({
          title: "Report load failed",
          message: error.message || "Unable to load report data.",
        });
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadData();
    return () => {
      active = false;
    };
  }, [pushToast]);

  const normalizedBookings = useMemo(
    () =>
      bookings.map((booking) => ({
        id: booking?.id,
        revenue: Number(booking?.total || 0),
        status: String(booking?.status || "Unknown"),
        movie: firstNonEmpty(booking?.movie, booking?.movie_title, "Unknown"),
        vendor: firstNonEmpty(booking?.vendor, booking?.vendor_name, "Unknown"),
        date: normalizeIsoDate(
          booking?.bookingDate || booking?.date || booking?.createdAt || booking?.created_at
        ),
      })),
    [bookings]
  );

  const filteredBookings = useMemo(() => {
    return normalizedBookings.filter((booking) => {
      if (startDate && booking.date && booking.date < startDate) return false;
      if (endDate && booking.date && booking.date > endDate) return false;
      if (selectedVendor && booking.vendor !== selectedVendor) return false;
      if (selectedMovie && booking.movie !== selectedMovie) return false;
      return true;
    });
  }, [normalizedBookings, startDate, endDate, selectedVendor, selectedMovie]);

  const reportHighlights = useMemo(() => {
    const revenue = filteredBookings.reduce((sum, booking) => sum + booking.revenue, 0);
    const bookingsCount = filteredBookings.length;
    const cancelled = filteredBookings.filter((booking) => booking.status === "Cancelled").length;
    const cancellationRate = bookingsCount > 0 ? (cancelled / bookingsCount) * 100 : 0;

    const movieAgg = new Map();
    const vendorAgg = new Map();

    filteredBookings.forEach((booking) => {
      const movieCurrent = movieAgg.get(booking.movie) || { title: booking.movie, revenue: 0, bookings: 0 };
      movieCurrent.revenue += booking.revenue;
      movieCurrent.bookings += 1;
      movieAgg.set(booking.movie, movieCurrent);

      const vendorCurrent = vendorAgg.get(booking.vendor) || { name: booking.vendor, revenue: 0, bookings: 0 };
      vendorCurrent.revenue += booking.revenue;
      vendorCurrent.bookings += 1;
      vendorAgg.set(booking.vendor, vendorCurrent);
    });

    const topMovies = Array.from(movieAgg.values())
      .sort((left, right) => right.revenue - left.revenue)
      .slice(0, 8);

    const topVendors = Array.from(vendorAgg.values())
      .sort((left, right) => right.revenue - left.revenue)
      .slice(0, 8);

    return {
      revenue,
      bookings: bookingsCount,
      cancellationRate,
      topMovies,
      topVendors,
    };
  }, [filteredBookings]);

  const vendorOptions = useMemo(() => {
    const names = new Set(
      vendors
        .map((vendor) => String(vendor?.name || "").trim())
        .filter(Boolean)
    );
    normalizedBookings.forEach((booking) => {
      if (booking.vendor) names.add(booking.vendor);
    });
    return Array.from(names).sort((a, b) => a.localeCompare(b));
  }, [vendors, normalizedBookings]);

  const movieOptions = useMemo(() => {
    const titles = new Set(
      movies
        .map((movie) => String(movie?.title || movie?.name || "").trim())
        .filter(Boolean)
    );
    normalizedBookings.forEach((booking) => {
      if (booking.movie) titles.add(booking.movie);
    });
    return Array.from(titles).sort((a, b) => a.localeCompare(b));
  }, [movies, normalizedBookings]);

  const handleExportPdf = () => {
    window.print();
    pushToast({ title: "Export started", message: "Print dialog opened for PDF export." });
  };

  const handleExportCsv = () => {
    const lines = [
      "metric,value",
      `total_revenue,${reportHighlights.revenue}`,
      `total_bookings,${reportHighlights.bookings}`,
      `cancellation_rate,${reportHighlights.cancellationRate.toFixed(2)}`,
      "",
      "top_movies_title,revenue,bookings",
      ...reportHighlights.topMovies.map(
        (movie) => `${escapeCsv(movie.title)},${movie.revenue},${movie.bookings}`
      ),
      "",
      "top_vendors_name,revenue,bookings",
      ...reportHighlights.topVendors.map(
        (vendor) => `${escapeCsv(vendor.name)},${vendor.revenue},${vendor.bookings}`
      ),
    ];

    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `admin-report-${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);

    pushToast({ title: "CSV exported", message: "Report CSV downloaded." });
  };

  const handleApplyFilters = () => {
    setStartDate(draftStartDate);
    setEndDate(draftEndDate);
    setSelectedVendor(draftVendor);
    setSelectedMovie(draftMovie);
    pushToast({ title: "Filters applied", message: "Report view refreshed." });
  };

  return (
    <>
      <AdminPageHeader
        title="Reports & Analytics"
        subtitle="Revenue, booking trends, and performance insights."
      >
        <button type="button" className="btn btn-outline-light admin-btn" onClick={handleExportPdf}>
          <Download size={16} className="me-2" />
          Export PDF
        </button>
        <button type="button" className="btn btn-outline-light admin-btn" onClick={handleExportCsv}>
          <Download size={16} className="me-2" />
          Export CSV
        </button>
      </AdminPageHeader>

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div className="d-flex gap-2 flex-wrap admin-filter-row">
            <input
              type="date"
              className="form-control"
              value={draftStartDate}
              onChange={(event) => setDraftStartDate(event.target.value)}
            />
            <input
              type="date"
              className="form-control"
              value={draftEndDate}
              onChange={(event) => setDraftEndDate(event.target.value)}
            />
            <select
              className="form-select"
              value={draftVendor}
              onChange={(event) => setDraftVendor(event.target.value)}
            >
              <option value="">All vendors</option>
              {vendorOptions.map((vendorName) => (
                <option key={vendorName} value={vendorName}>
                  {vendorName}
                </option>
              ))}
            </select>
            <select
              className="form-select"
              value={draftMovie}
              onChange={(event) => setDraftMovie(event.target.value)}
            >
              <option value="">All movies</option>
              {movieOptions.map((movieTitle) => (
                <option key={movieTitle} value={movieTitle}>
                  {movieTitle}
                </option>
              ))}
            </select>
          </div>
          <button type="button" className="btn btn-primary admin-btn" onClick={handleApplyFilters}>
            <Filter size={16} className="me-2" />
            Apply Filters
          </button>
        </div>

        <div className="admin-grid-3">
          <div className="admin-card">
            <div className="admin-kpi">
              <strong>{loading ? "-" : `Rs ${reportHighlights.revenue.toLocaleString()}`}</strong>
              <small>Total Revenue</small>
            </div>
          </div>
          <div className="admin-card">
            <div className="admin-kpi">
              <strong>{loading ? "-" : reportHighlights.bookings}</strong>
              <small>Total Bookings</small>
            </div>
          </div>
          <div className="admin-card">
            <div className="admin-kpi">
              <strong>
                {loading ? "-" : `${reportHighlights.cancellationRate.toFixed(1)}%`}
              </strong>
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
                {!loading && reportHighlights.topMovies.length === 0 ? (
                  <tr>
                    <td colSpan="3">No movie analytics for selected filters.</td>
                  </tr>
                ) : null}
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
                {!loading && reportHighlights.topVendors.length === 0 ? (
                  <tr>
                    <td colSpan="3">No vendor analytics for selected filters.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </>
  );
}

function escapeCsv(value) {
  const text = String(value ?? "");
  if (text.includes(",") || text.includes("\"") || text.includes("\n")) {
    return `"${text.replaceAll("\"", "\"\"")}"`;
  }
  return text;
}

function firstNonEmpty(...values) {
  for (const value of values) {
    const text = String(value ?? "").trim();
    if (text) return text;
  }
  return "";
}

function normalizeIsoDate(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";

  const shortIso = text.match(/^(\d{4}-\d{2}-\d{2})/);
  if (shortIso) return shortIso[1];

  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return "";
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
