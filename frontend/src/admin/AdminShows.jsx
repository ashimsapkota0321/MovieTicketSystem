import { useEffect, useState } from "react";
import { CalendarPlus, Pencil, XCircle } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import AdminModal from "./components/AdminModal";
import ConfirmModal from "./components/ConfirmModal";
import { useAdminToast } from "./AdminToastContext";
import { createShow, deleteShow, fetchVendorsAdmin } from "../lib/catalogApi";
import { useAppContext } from "../context/Appcontext";

export default function AdminShows() {
  const { pushToast } = useAdminToast();
  const ctx = safeUseAppContext();
  const movies = ctx?.movies ?? [];
  const shows = ctx?.showtimes ?? [];
  const refreshCatalog = ctx?.refreshCatalog ?? (async () => {});

  const [vendors, setVendors] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [showToDelete, setShowToDelete] = useState(null);
  const [editingShow, setEditingShow] = useState(null);
  const [form, setForm] = useState(() => buildEmptyShow(movies, vendors));

  useEffect(() => {
    let active = true;
    const loadVendors = async () => {
      try {
        const list = await fetchVendorsAdmin();
        if (active) {
          setVendors(list);
          setForm((prev) => ({
            ...prev,
            vendorId: prev.vendorId || list[0]?.id || "",
          }));
        }
      } catch (error) {
        console.log(error);
      }
    };
    loadVendors();
    return () => {
      active = false;
    };
  }, []);

  const handleSave = async () => {
    if (!form.movieId || !form.vendorId) {
      pushToast({ title: "Missing data", message: "Select a movie and vendor." });
      return;
    }

    const payload = {
      movieId: form.movieId,
      vendorId: form.vendorId,
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
      if (editingShow?.id) {
        await deleteShow(editingShow.id);
      }
      await refreshCatalog();
      setShowModal(false);
      setEditingShow(null);
      pushToast({
        title: editingShow ? "Show updated" : "Show created",
        message: editingShow
          ? "Show schedule updated successfully."
          : "Show scheduled successfully.",
      });
    } catch (error) {
      pushToast({
        title: editingShow ? "Update failed" : "Create failed",
        message: error.message || "Unable to save show.",
      });
    }
  };

  const openCreateModal = () => {
    setEditingShow(null);
    setForm(buildEmptyShow(movies, vendors));
    setShowModal(true);
  };

  const openEditModal = (show) => {
    setEditingShow(show);
    setForm(buildFormFromShow(show, movies, vendors));
    setShowModal(true);
  };

  const handleDelete = async () => {
    if (!showToDelete?.id) return;
    try {
      await deleteShow(showToDelete.id);
      await refreshCatalog();
      setShowConfirm(false);
      pushToast({ title: "Show cancelled", message: "Show removed from schedule." });
    } catch (error) {
      pushToast({
        title: "Delete failed",
        message: error.message || "Unable to delete show.",
      });
    }
  };

  return (
    <>
      <AdminPageHeader
        title="Manage Shows"
        subtitle="Create, edit, or cancel shows across all vendors."
      >
        <button
          type="button"
          className="btn btn-primary admin-btn"
          onClick={openCreateModal}
        >
          <CalendarPlus size={16} className="me-2" />
          Create Show
        </button>
      </AdminPageHeader>

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div className="d-flex gap-2 flex-wrap admin-filter-row">
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
            <input type="date" className="form-control" defaultValue={form.date} />
          </div>
          <div className="text-muted small">{shows.length} shows scheduled</div>
        </div>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Movie</th>
                <th>Vendor</th>
                <th>Hall</th>
                <th>Date</th>
                <th>Slot</th>
                <th>Start/End</th>
                <th>Screen</th>
                <th>Price</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {shows.map((show) => (
                <tr key={show.id}>
                  <td>
                    <div className="fw-semibold">{show.movie}</div>
                    <small className="text-muted">{show.id}</small>
                  </td>
                  <td>{show.vendor}</td>
                  <td>{show.hall}</td>
                  <td>{show.date}</td>
                  <td>{show.slot || guessSlot(show.start)}</td>
                  <td>
                    {show.start} - {show.end}
                  </td>
                  <td>{show.screenType}</td>
                  <td>Rs {show.price}</td>
                  <td>
                    <span
                      className={`badge-soft ${
                        show.status === "Open"
                          ? "success"
                          : show.status === "Sold Out"
                          ? "warning"
                          : "info"
                      }`}
                    >
                      {show.status}
                    </span>
                  </td>
                  <td>
                    <div className="d-flex gap-2">
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => openEditModal(show)}
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => {
                          setShowToDelete(show);
                          setShowConfirm(true);
                        }}
                      >
                        <XCircle size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {shows.length === 0 ? (
                <tr>
                  <td colSpan="10">No shows scheduled yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <nav className="d-flex justify-content-between align-items-center mt-3">
          <span className="text-muted small">Page 1 of 1</span>
          <ul className="pagination mb-0">
            <li className="page-item disabled"><span className="page-link">Prev</span></li>
            <li className="page-item active"><span className="page-link">1</span></li>
            <li className="page-item disabled"><span className="page-link">Next</span></li>
          </ul>
        </nav>
      </section>

      <AdminModal
        show={showModal}
        title={editingShow ? "Edit Show" : "Create Show"}
        onClose={() => {
          setShowModal(false);
          setEditingShow(null);
        }}
        footer={
          <>
            <button
              type="button"
              className="btn btn-outline-light"
              onClick={() => {
                setShowModal(false);
                setEditingShow(null);
              }}
            >
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={handleSave}>
              {editingShow ? "Update Show" : "Save Show"}
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
            <label className="form-label">Vendor</label>
            <select
              className="form-select"
              value={form.vendorId}
              onChange={(event) => setForm((prev) => ({ ...prev, vendorId: event.target.value }))}
            >
              {vendors.map((vendor) => (
                <option key={vendor.id} value={vendor.id}>
                  {vendor.name}
                </option>
              ))}
            </select>
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
        title="Cancel show?"
        description="This show will be removed from active listings."
        onCancel={() => setShowConfirm(false)}
        onConfirm={handleDelete}
      />
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

function buildEmptyShow(movies, vendors) {
  const firstMovie = (movies || [])[0];
  const firstVendor = (vendors || [])[0];
  const today = new Date().toISOString().slice(0, 10);
  return {
    movieId: firstMovie?.id || "",
    vendorId: firstVendor?.id || "",
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

function buildFormFromShow(show, movies, vendors) {
  const movieId = show?.movieId || movies.find((movie) => movie.title === show?.movie)?.id || "";
  const vendorId = show?.vendorId || vendors.find((vendor) => vendor.name === show?.vendor)?.id || "";
  return {
    movieId,
    vendorId,
    hall: show?.hall || "Hall A",
    date: show?.date || new Date().toISOString().slice(0, 10),
    slot: show?.slot || guessSlot(show?.start),
    start: show?.start || "18:30",
    end: show?.end || "20:30",
    screenType: show?.screenType || "Standard",
    price: String(show?.price ?? "450"),
    status: show?.status || "Open",
    listingStatus: show?.listingStatus || "Now Showing",
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
