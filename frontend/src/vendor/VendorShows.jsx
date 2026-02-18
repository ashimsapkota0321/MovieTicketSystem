import { useMemo, useState } from "react";
import { CalendarPlus, Trash2 } from "lucide-react";
import AdminModal from "../admin/components/AdminModal";
import ConfirmModal from "../admin/components/ConfirmModal";
import { createShow, deleteShow } from "../lib/catalogApi";
import { useAppContext } from "../context/Appcontext";

export default function VendorShows() {
  const ctx = safeUseAppContext();
  const movies = ctx?.movies ?? [];
  const shows = ctx?.showtimes ?? [];
  const refreshCatalog = ctx?.refreshCatalog ?? (async () => {});

  const vendor = getStoredVendor();
  const vendorName = vendor?.name || vendor?.theatre || vendor?.username || "Vendor";
  const vendorId = vendor?.id || "";

  const vendorShows = useMemo(
    () =>
      shows.filter((show) => {
        if (vendorId && String(show.vendorId) === String(vendorId)) return true;
        return String(show.vendor || "").trim().toLowerCase() === String(vendorName).trim().toLowerCase();
      }),
    [shows, vendorId, vendorName]
  );

  const [showModal, setShowModal] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [showToDelete, setShowToDelete] = useState(null);
  const [form, setForm] = useState(() => buildEmptyShow(movies));

  const handleSave = async () => {
    if (!form.movieId) return;
    const payload = {
      movieId: form.movieId,
      vendorId: vendorId,
      hall: form.hall || "Hall A",
      date: form.date,
      slot: form.slot || guessSlot(form.start),
      start: form.start,
      end: form.end,
      screenType: form.screenType,
      price: form.price,
      status: form.status,
      listingStatus: form.listingStatus,
    };

    try {
      await createShow(payload);
      await refreshCatalog();
      setShowModal(false);
    } catch (error) {
      console.log(error);
    }
  };

  const handleDelete = async () => {
    if (!showToDelete?.id) return;
    try {
      await deleteShow(showToDelete.id);
      await refreshCatalog();
      setShowConfirm(false);
    } catch (error) {
      console.log(error);
    }
  };

  return (
    <div className="vendor-dashboard">
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3">
        <div>
          <h2 className="mb-1">Show Management</h2>
          <p className="text-muted mb-0">
            Manage your cinema schedule, pricing, and listing status.
          </p>
        </div>
      </div>
      <div className="vendor-breadcrumb">
        <span>Shows</span>
        <span className="vendor-dot">&#8226;</span>
        <span>Schedule</span>
      </div>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Show Management</h3>
            <p>Add now showing and coming soon shows for your cinema.</p>
          </div>
          <button
            type="button"
            className="vendor-chip"
            onClick={() => {
              setForm(buildEmptyShow(movies));
              setShowModal(true);
            }}
          >
            <CalendarPlus size={16} />
            Add Show
          </button>
        </div>

        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Movie</th>
                <th>Date</th>
                <th>Time</th>
                <th>Hall</th>
                <th>Screen</th>
                <th>Price</th>
                <th>Status</th>
                <th>Listing</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {vendorShows.map((show) => (
                <tr key={show.id}>
                  <td className="fw-semibold">{show.movie}</td>
                  <td>{show.date}</td>
                  <td>
                    {show.start} - {show.end}
                  </td>
                  <td>{show.hall}</td>
                  <td>{show.screenType}</td>
                  <td>Rs {show.price}</td>
                  <td>{show.status}</td>
                  <td>{show.listingStatus || "Now Showing"}</td>
                  <td>
                    <button
                      type="button"
                      className="vendor-icon-btn"
                      onClick={() => {
                        setShowToDelete(show);
                        setShowConfirm(true);
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
              {vendorShows.length === 0 ? (
                <tr>
                  <td colSpan="9">No shows added yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <AdminModal
        show={showModal}
        title="Add Show"
        onClose={() => setShowModal(false)}
        footer={
          <>
            <button type="button" className="btn btn-outline-light" onClick={() => setShowModal(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={handleSave}>
              Save Show
            </button>
          </>
        }
      >
        <div className="row g-3">
          <div className="col-md-6">
            <label className="form-label">Movie</label>
            <select
              className="form-select"
              value={form.movieId}
              onChange={(event) => setForm((prev) => ({ ...prev, movieId: event.target.value }))}
            >
              {movies.map((movie) => (
                <option key={movie.id} value={movie.id}>
                  {movie.title}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-6">
            <label className="form-label">Cinema</label>
            <input className="form-control" value={vendorName} disabled />
          </div>
          <div className="col-md-4">
            <label className="form-label">Hall</label>
            <input
              className="form-control"
              value={form.hall}
              onChange={(event) => setForm((prev) => ({ ...prev, hall: event.target.value }))}
            />
          </div>
          <div className="col-md-4">
            <label className="form-label">Date</label>
            <input
              type="date"
              className="form-control"
              value={form.date}
              onChange={(event) => setForm((prev) => ({ ...prev, date: event.target.value }))}
            />
          </div>
          <div className="col-md-4">
            <label className="form-label">Slot</label>
            <select
              className="form-select"
              value={form.slot}
              onChange={(event) => setForm((prev) => ({ ...prev, slot: event.target.value }))}
            >
              <option>Morning</option>
              <option>Matinee</option>
              <option>Evening</option>
              <option>Night</option>
            </select>
          </div>
          <div className="col-md-4">
            <label className="form-label">Start time</label>
            <input
              type="time"
              className="form-control"
              value={form.start}
              onChange={(event) => setForm((prev) => ({ ...prev, start: event.target.value }))}
            />
          </div>
          <div className="col-md-4">
            <label className="form-label">End time</label>
            <input
              type="time"
              className="form-control"
              value={form.end}
              onChange={(event) => setForm((prev) => ({ ...prev, end: event.target.value }))}
            />
          </div>
          <div className="col-md-4">
            <label className="form-label">Screen</label>
            <select
              className="form-select"
              value={form.screenType}
              onChange={(event) => setForm((prev) => ({ ...prev, screenType: event.target.value }))}
            >
              <option>Standard</option>
              <option>Dolby Atmos</option>
              <option>IMAX</option>
              <option>4K Laser</option>
            </select>
          </div>
          <div className="col-md-6">
            <label className="form-label">Price (Rs)</label>
            <input
              className="form-control"
              value={form.price}
              onChange={(event) => setForm((prev) => ({ ...prev, price: event.target.value }))}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Status</label>
            <select
              className="form-select"
              value={form.status}
              onChange={(event) => setForm((prev) => ({ ...prev, status: event.target.value }))}
            >
              <option>Open</option>
              <option>Scheduled</option>
              <option>Sold Out</option>
            </select>
          </div>
          <div className="col-md-6">
            <label className="form-label">Listing</label>
            <select
              className="form-select"
              value={form.listingStatus}
              onChange={(event) => setForm((prev) => ({ ...prev, listingStatus: event.target.value }))}
            >
              <option value="Now Showing">Now Showing</option>
              <option value="Coming Soon">Coming Soon</option>
            </select>
          </div>
        </div>
      </AdminModal>

      <ConfirmModal
        show={showConfirm}
        title="Remove show?"
        description="This show will be removed from your schedule."
        onCancel={() => setShowConfirm(false)}
        onConfirm={handleDelete}
      />
    </div>
  );
}

function safeUseAppContext() {
  try {
    return useAppContext?.();
  } catch {
    return null;
  }
}

function buildEmptyShow(movies) {
  const firstMovie = (movies || [])[0];
  const today = new Date().toISOString().slice(0, 10);
  return {
    movieId: firstMovie?.id || "",
    hall: "Hall A",
    date: today,
    slot: "Evening",
    start: "18:30",
    end: "20:30",
    screenType: "Standard",
    price: "450",
    status: "Open",
    listingStatus: "Now Showing",
  };
}

function guessSlot(startTime) {
  const hours = Number(String(startTime || "").split(":")[0]);
  if (Number.isNaN(hours)) return "Evening";
  if (hours < 12) return "Morning";
  if (hours < 16) return "Matinee";
  if (hours < 20) return "Evening";
  return "Night";
}

function getStoredVendor() {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem("vendor");
    return JSON.parse(raw || "null");
  } catch {
    return null;
  }
}
