import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Armchair, CalendarPlus, MoveRight, Sparkles, Trash2 } from "lucide-react";
import AdminModal from "../admin/components/AdminModal";
import ConfirmModal from "../admin/components/ConfirmModal";
import {
  createVendorHall,
  createShow,
  createVendorMovie,
  deleteShow,
  fetchVendorHalls,
  fetchVendorQuickHallSwapPreview,
  runVendorQuickHallSwap,
} from "../lib/catalogApi";
import { useAppContext } from "../context/Appcontext";

const EMPTY_LIST = [];

export default function VendorShows() {
  const navigate = useNavigate();
  const ctx = useSafeAppContext();
  const movies = ctx?.movies ?? EMPTY_LIST;
  const shows = ctx?.showtimes ?? EMPTY_LIST;
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
  const [hallRecords, setHallRecords] = useState([]);
  const [hallsLoading, setHallsLoading] = useState(false);
  const [hallActionLoading, setHallActionLoading] = useState(false);
  const hallOptions = useMemo(() => {
    const halls = new Set(
      (Array.isArray(hallRecords) ? hallRecords : [])
        .map((item) => normalizeHallName(item?.hall))
        .filter(Boolean)
    );
    return Array.from(halls).sort((left, right) =>
      left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" })
    );
  }, [hallRecords]);

  const [showModal, setShowModal] = useState(false);
  const [movieModal, setMovieModal] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [hallSwapModal, setHallSwapModal] = useState(false);
  const [showToDelete, setShowToDelete] = useState(null);
  const [showToSwap, setShowToSwap] = useState(null);
  const [hallSwapPreview, setHallSwapPreview] = useState(null);
  const [swapLoading, setSwapLoading] = useState(false);
  const [swapRunning, setSwapRunning] = useState(false);
  const [swapTargetHall, setSwapTargetHall] = useState("");
  const [form, setForm] = useState(() => buildEmptyShow(movies, hallOptions));
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [movieForm, setMovieForm] = useState(() => buildEmptyMovie());
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [searchParams] = useSearchParams();
  const queryFromUrl = String(searchParams.get("q") || "");

  useEffect(() => {
    setQuery(queryFromUrl);
  }, [queryFromUrl]);

  const filteredVendorShows = useMemo(() => {
    const term = String(query || "").trim().toLowerCase();
    if (!term) return vendorShows;
    return vendorShows.filter((show) => {
      const haystack = [
        show?.movie,
        show?.date,
        show?.start,
        show?.end,
        show?.hall,
        show?.screenType,
        show?.status,
        show?.listingStatus,
      ]
        .map((value) => String(value || "").toLowerCase())
        .join(" ");
      return haystack.includes(term);
    });
  }, [vendorShows, query]);

  const showStats = useMemo(() => {
    const nowShowing = vendorShows.filter(
      (show) => String(show?.listingStatus || "").toLowerCase().includes("now")
    ).length;
    const soldOut = vendorShows.filter(
      (show) => String(show?.status || "").toLowerCase() === "sold out"
    ).length;
    const halls = new Set(
      vendorShows.map((show) => String(show?.hall || "").trim()).filter(Boolean)
    ).size;
    return { nowShowing, soldOut, halls };
  }, [vendorShows]);
  useEffect(() => {
    if (!vendorId) return;
    let active = true;
    const loadHalls = async () => {
      setHallsLoading(true);
      try {
        const payload = await fetchVendorHalls({ vendor_id: vendorId });
        if (!active) return;
        setHallRecords(Array.isArray(payload?.halls) ? payload.halls : []);
      } catch {
        if (!active) return;
        setHallRecords([]);
      } finally {
        if (active) setHallsLoading(false);
      }
    };
    loadHalls();
    return () => {
      active = false;
    };
  }, [vendorId]);

  useEffect(() => {
    setForm((prev) => {
      const normalized = normalizeHallName(prev.hall);
      const isValid =
        normalized &&
        hallOptions.some((hall) => hall.toLowerCase() === normalized.toLowerCase());
      if (isValid) return prev;
      return { ...prev, hall: hallOptions[0] || "" };
    });
  }, [hallOptions]);

  const selectedHallMeta = useMemo(() => {
    const normalized = normalizeHallName(form.hall).toLowerCase();
    if (!normalized) return null;
    return (
      hallRecords.find(
        (item) => normalizeHallName(item?.hall).toLowerCase() === normalized
      ) || null
    );
  }, [hallRecords, form.hall]);

  const handleAddHall = async () => {
    if (!vendorId || hallActionLoading) return;
    setErrorMessage("");
    setNotice("");
    setHallActionLoading(true);
    try {
      const result = await createVendorHall({ vendor_id: vendorId });
      const createdHall = normalizeHallName(result?.hall?.hall);
      const hallsPayload = await fetchVendorHalls({ vendor_id: vendorId });
      const nextHalls = Array.isArray(hallsPayload?.halls) ? hallsPayload.halls : [];
      setHallRecords(nextHalls);
      if (createdHall) {
        setForm((prev) => ({ ...prev, hall: createdHall }));
        setNotice(`${createdHall} created.`);
      }
    } catch (error) {
      setErrorMessage(error.message || "Unable to add hall.");
    } finally {
      setHallActionLoading(false);
    }
  };

  const handleBookSeats = (show) => {
    if (!show) return;

    const matchedMovie = findMovieForShow(movies, show);
    const moviePayload = matchedMovie
      ? {
          ...matchedMovie,
          id: matchedMovie.id || show.movieId || show.movie_id,
          title: matchedMovie.title || show.movie || "Movie",
        }
      : {
          id: show.movieId || show.movie_id || "",
          title: show.movie || "Movie",
        };

    navigate("/booking", {
      state: {
        movie: moviePayload,
        vendor: {
          id: vendorId,
          name: vendorName,
        },
        show: {
          id: show.id,
          date: show.date,
          start: show.start,
          hall: show.hall,
          vendorId,
          movieId: moviePayload.id,
        },
        date: show.date,
        time: show.start,
        hall: show.hall,
        showId: show.id,
      },
    });
  };

  const handleSave = async () => {
    setErrorMessage("");
    setNotice("");
    if (!form.movieId) return;
    const resolvedHall = normalizeHallName(form.hall);
    if (!resolvedHall) {
      setErrorMessage("Please add a hall first.");
      return;
    }
    if (!hallOptions.some((hall) => hall.toLowerCase() === resolvedHall.toLowerCase())) {
      setErrorMessage("Please select a valid hall.");
      return;
    }
    const payload = {
      movieId: form.movieId,
      vendorId: vendorId,
      hall: resolvedHall,
      date: form.date,
      start: form.start,
      repeatDays: form.repeatDays,
    };

    if (showAdvanced) {
      payload.slot = form.slot || guessSlot(form.start);
      payload.screenType = form.screenType;
      payload.status = form.status;
      payload.listingStatus = form.listingStatus;
      if (String(form.price || "").trim()) {
        payload.price = form.price;
      }
    }

    try {
      const result = await createShow(payload);
      await refreshCatalog();
      setShowModal(false);
      const createdCount = Number(result?.created_count || 0);
      const conflictCount = Array.isArray(result?.conflicts) ? result.conflicts.length : 0;
      if (result?.message) {
        setNotice(result.message);
      } else if (createdCount > 1) {
        setNotice(`Created ${createdCount} shows successfully.`);
      } else if (createdCount === 1) {
        setNotice("Show created successfully.");
      }
      if (createdCount > 0 && conflictCount > 0 && !result?.message) {
        setNotice(`Created ${createdCount} shows. Skipped ${conflictCount} duplicate timing(s).`);
      }
    } catch (error) {
      setErrorMessage(error.message || "Unable to create show.");
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

  const handleSaveMovie = async () => {
    if (!movieForm.title.trim()) return;
    const payload = new FormData();
    payload.append("title", movieForm.title.trim());
    payload.append("duration", movieForm.duration.trim());
    payload.append("genre", movieForm.genre.trim());
    payload.append("language", movieForm.language.trim());
    payload.append("rating", movieForm.rating.trim());
    payload.append("releaseDate", movieForm.releaseDate || "");
    payload.append("status", movieForm.status || "COMING_SOON");
    payload.append("synopsis", movieForm.synopsis?.trim() || "");
    payload.append("trailerUrl", movieForm.trailerUrl?.trim() || "");
    if (movieForm.posterFile) {
      payload.append("poster_image", movieForm.posterFile);
    }

    try {
      const created = await createVendorMovie(payload);
      await refreshCatalog();
      setMovieModal(false);
      setMovieForm(buildEmptyMovie());
      if (created?.id) {
        setForm((prev) => ({ ...prev, movieId: String(created.id) }));
      }
    } catch (error) {
      console.log(error);
    }
  };

  const openHallSwapModal = async (show) => {
    if (!show?.id) return;
    setShowToSwap(show);
    setHallSwapModal(true);
    setSwapTargetHall("");
    setSwapLoading(true);
    setErrorMessage("");
    try {
      const preview = await fetchVendorQuickHallSwapPreview(show.id);
      setHallSwapPreview(preview);
      const recommended = (preview?.candidates || []).find((item) => item?.recommended);
      if (recommended?.hall) {
        setSwapTargetHall(recommended.hall);
      }
    } catch (error) {
      setErrorMessage(error.message || "Unable to load hall swap options.");
      setHallSwapPreview(null);
    } finally {
      setSwapLoading(false);
    }
  };

  const handleQuickSwap = async (targetHallValue) => {
    const targetHall = String(targetHallValue || swapTargetHall || "").trim();
    if (!showToSwap?.id || !targetHall) {
      setErrorMessage("Please select a target hall.");
      return;
    }

    setSwapRunning(true);
    setErrorMessage("");
    setNotice("");
    try {
      const result = await runVendorQuickHallSwap(showToSwap.id, { target_hall: targetHall });
      setNotice(result?.message || `Show swapped to ${targetHall}.`);
      setHallSwapModal(false);
      setHallSwapPreview(null);
      setSwapTargetHall("");
      setShowToSwap(null);
      await refreshCatalog();
    } catch (error) {
      setErrorMessage(error.message || "Quick hall swap failed.");
    } finally {
      setSwapRunning(false);
    }
  };

  return (
    <div className="vendor-dashboard">
      <div className="vendor-marketing-hero mb-3">
        <div>
          <p className="vendor-marketing-eyebrow mb-1">Scheduling Control</p>
          <h2 className="mb-1">Show Management</h2>
          <p className="text-muted mb-0">
            Handle scheduling and trigger one-click hall upgrades when demand spikes.
          </p>
        </div>
        <div className="vendor-marketing-metrics">
          <div className="vendor-marketing-metric">
            <span>Total Shows</span>
            <strong>{vendorShows.length}</strong>
          </div>
          <div className="vendor-marketing-metric">
            <span>Now Showing</span>
            <strong>{showStats.nowShowing}</strong>
          </div>
          <div className="vendor-marketing-metric">
            <span>Sold Out / Halls</span>
            <strong>
              {showStats.soldOut} / {showStats.halls}
            </strong>
          </div>
        </div>
      </div>

      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3">
        <div>
          <p className="vendor-breadcrumb mb-0">
            <span>Shows</span>
            <span className="vendor-dot">&#8226;</span>
            <span>Schedule</span>
          </p>
        </div>
      </div>

      <section className="vendor-card">
        {errorMessage ? <div className="alert alert-danger mb-3">{errorMessage}</div> : null}
        {notice ? <div className="alert alert-success mb-3">{notice}</div> : null}
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3 vendor-filter-row-wrap">
          <input
            className="form-control"
            style={{ maxWidth: 340 }}
            placeholder="Search shows"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="text-muted small">{filteredVendorShows.length} shows</div>
        </div>

        <div className="vendor-card-header">
          <div>
            <h3>Show Management</h3>
            <p>Add now showing and coming soon shows for your cinema.</p>
          </div>
          <button
            type="button"
            className="vendor-chip"
            onClick={() => {
              setMovieForm(buildEmptyMovie());
              setMovieModal(true);
            }}
          >
            <CalendarPlus size={16} />
            Add Movie
          </button>
          <button
            type="button"
            className="vendor-chip"
            onClick={() => {
              setForm(buildEmptyShow(movies, hallOptions));
              setShowAdvanced(false);
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
              {filteredVendorShows.map((show) => (
                <tr key={show.id}>
                  <td className="fw-semibold">{show.movie}</td>
                  <td>{show.date}</td>
                  <td>
                    {show.start} - {show.end}
                  </td>
                  <td>{show.hall}</td>
                  <td>{show.screenType || "-"}</td>
                  <td>{show.price != null && show.price !== "" ? `Rs ${show.price}` : "-"}</td>
                  <td>{show.status}</td>
                  <td>{show.listingStatus || "Now Showing"}</td>
                  <td>
                    <button
                      type="button"
                      className="vendor-icon-btn me-2"
                      title="Book seats"
                      aria-label="Book seats"
                      onClick={() => handleBookSeats(show)}
                    >
                      <Armchair size={16} />
                    </button>
                    <button
                      type="button"
                      className="vendor-icon-btn me-2"
                      title="Quick hall swap"
                      aria-label="Quick hall swap"
                      onClick={() => openHallSwapModal(show)}
                    >
                      <MoveRight size={16} />
                    </button>
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
              {filteredVendorShows.length === 0 ? (
                <tr>
                  <td colSpan="9">No shows added yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <AdminModal
        show={movieModal}
        title="Add Movie"
        onClose={() => setMovieModal(false)}
        footer={
          <>
            <button type="button" className="btn btn-outline-light" onClick={() => setMovieModal(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={handleSaveMovie}>
              Save Movie
            </button>
          </>
        }
      >
        <div className="row g-3">
          <div className="col-md-8">
            <label className="form-label">Movie title</label>
            <input
              className="form-control"
              value={movieForm.title}
              onChange={(event) => setMovieForm((prev) => ({ ...prev, title: event.target.value }))}
            />
          </div>
          <div className="col-md-4">
            <label className="form-label">Duration</label>
            <input
              className="form-control"
              value={movieForm.duration}
              onChange={(event) => setMovieForm((prev) => ({ ...prev, duration: event.target.value }))}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Genre</label>
            <input
              className="form-control"
              value={movieForm.genre}
              onChange={(event) => setMovieForm((prev) => ({ ...prev, genre: event.target.value }))}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Language</label>
            <input
              className="form-control"
              value={movieForm.language}
              onChange={(event) => setMovieForm((prev) => ({ ...prev, language: event.target.value }))}
            />
          </div>
          <div className="col-md-4">
            <label className="form-label">Rating</label>
            <input
              className="form-control"
              value={movieForm.rating}
              onChange={(event) => setMovieForm((prev) => ({ ...prev, rating: event.target.value }))}
            />
          </div>
          <div className="col-md-4">
            <label className="form-label">Release date</label>
            <input
              type="date"
              className="form-control"
              value={movieForm.releaseDate}
              onChange={(event) => setMovieForm((prev) => ({ ...prev, releaseDate: event.target.value }))}
            />
          </div>
          <div className="col-md-4">
            <label className="form-label">Status</label>
            <select
              className="form-select"
              value={movieForm.status}
              onChange={(event) => setMovieForm((prev) => ({ ...prev, status: event.target.value }))}
            >
              <option value="NOW_SHOWING">Now Showing</option>
              <option value="COMING_SOON">Coming Soon</option>
            </select>
          </div>
          <div className="col-12">
            <label className="form-label">Synopsis</label>
            <textarea
              className="form-control"
              rows="3"
              value={movieForm.synopsis}
              onChange={(event) => setMovieForm((prev) => ({ ...prev, synopsis: event.target.value }))}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Poster Image</label>
            <input
              type="file"
              accept="image/*"
              className="form-control"
              onChange={(event) =>
                setMovieForm((prev) => ({ ...prev, posterFile: event.target.files?.[0] || null }))
              }
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Trailer URL</label>
            <input
              className="form-control"
              value={movieForm.trailerUrl}
              onChange={(event) => setMovieForm((prev) => ({ ...prev, trailerUrl: event.target.value }))}
            />
          </div>
        </div>
      </AdminModal>

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
          <div className="col-md-6">
            <div className="d-flex align-items-center justify-content-between mb-1">
              <label className="form-label mb-0">Hall</label>
              <button
                type="button"
                className="btn btn-sm btn-outline-light"
                onClick={handleAddHall}
                disabled={hallActionLoading}
              >
                {hallActionLoading ? "Adding..." : "+ Add Hall"}
              </button>
            </div>
            <select
              className="form-select"
              value={form.hall}
              onChange={(event) => setForm((prev) => ({ ...prev, hall: event.target.value }))}
            >
              <option value="">Select hall</option>
              {hallOptions.map((hall) => (
                <option key={hall} value={hall}>
                  {hall}
                </option>
              ))}
            </select>
            <small className="text-muted d-block mt-1">
              {hallsLoading ? "Loading halls..." : "Use + Add Hall to create Hall A, Hall B, Hall C..."}
            </small>
            {selectedHallMeta ? (
              <small className="text-muted d-block mt-1">
                Layout: {Number(selectedHallMeta?.total_rows || 0)} rows x {Number(selectedHallMeta?.total_columns || 0)} cols | Seats: {Number(selectedHallMeta?.seat_count || 0)}
              </small>
            ) : null}
          </div>
          <div className="col-md-3">
            <label className="form-label">Date</label>
            <input
              type="date"
              className="form-control"
              value={form.date}
              onChange={(event) => setForm((prev) => ({ ...prev, date: event.target.value }))}
            />
          </div>
          <div className="col-md-3">
            <label className="form-label">Start time</label>
            <input
              type="time"
              className="form-control"
              value={form.start}
              onChange={(event) => setForm((prev) => ({ ...prev, start: event.target.value }))}
            />
          </div>
          <div className="col-12">
            <div className="d-flex align-items-center justify-content-between">
              <small className="text-muted">End time is computed automatically from movie duration.</small>
              <button
                type="button"
                className="btn btn-sm btn-outline-light"
                onClick={() => setShowAdvanced((prev) => !prev)}
              >
                {showAdvanced ? "Hide Advanced" : "Show Advanced"}
              </button>
            </div>
          </div>
          {showAdvanced ? (
            <>
              <div className="col-md-3">
                <label className="form-label">Repeat for days</label>
                <input
                  type="number"
                  min="1"
                  max="60"
                  className="form-control"
                  value={form.repeatDays}
                  onChange={(event) => setForm((prev) => ({ ...prev, repeatDays: event.target.value }))}
                />
              </div>
              <div className="col-md-3">
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
              <div className="col-md-3">
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
              <div className="col-md-3">
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
            </>
          ) : null}
        </div>
      </AdminModal>

      <ConfirmModal
        show={showConfirm}
        title="Remove show?"
        description="This show will be removed from your schedule."
        onCancel={() => setShowConfirm(false)}
        onConfirm={handleDelete}
      />

      <AdminModal
        show={hallSwapModal}
        title="Quick Hall Swap"
        onClose={() => {
          if (swapRunning) return;
          setHallSwapModal(false);
          setHallSwapPreview(null);
          setSwapTargetHall("");
          setShowToSwap(null);
        }}
        footer={
          <>
            <button
              type="button"
              className="btn btn-outline-light"
              disabled={swapRunning}
              onClick={() => {
                setHallSwapModal(false);
                setHallSwapPreview(null);
                setSwapTargetHall("");
                setShowToSwap(null);
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={swapRunning || !swapTargetHall}
              onClick={() => handleQuickSwap(swapTargetHall)}
            >
              {swapRunning ? "Swapping..." : "Swap Now"}
            </button>
          </>
        }
      >
        <div className="vendor-hall-swap-modal">
          <p className="text-muted mb-2">
            Move this show to a larger hall and auto-transfer existing bookings to equivalent seats.
          </p>

          {swapLoading ? <div className="text-muted">Loading hall options...</div> : null}

          {!swapLoading && hallSwapPreview?.source ? (
            <div className="vendor-hall-swap-source mb-3">
              <div>
                <strong>Current Hall:</strong> {hallSwapPreview.source.hall}
              </div>
              <div>
                <strong>Capacity:</strong> {hallSwapPreview.source.capacity || 0}
              </div>
              <div>
                <strong>Booked Seats To Transfer:</strong> {hallSwapPreview.source.booked_seats || 0}
              </div>
            </div>
          ) : null}

          {!swapLoading ? (
            <div className="vendor-hall-swap-grid">
              {(hallSwapPreview?.candidates || []).map((candidate) => (
                <div
                  key={candidate.hall}
                  className={`vendor-hall-swap-card ${
                    swapTargetHall === candidate.hall ? "selected" : ""
                  } ${candidate.can_fit ? "fit" : "blocked"}`}
                >
                  <div className="vendor-hall-swap-card-head">
                    <h4>{candidate.hall}</h4>
                    {candidate.recommended ? (
                      <span className="vendor-chip">
                        <Sparkles size={12} />
                        Recommended
                      </span>
                    ) : null}
                  </div>
                  <p className="mb-1 text-muted">Capacity: {candidate.capacity || 0}</p>
                  <p className="mb-1 text-muted">Free seats now: {candidate.free_capacity || 0}</p>
                  <p className="mb-2 text-muted">Screen: {candidate.screen_type || "-"}</p>
                  {candidate.timing_conflict ? (
                    <div className="vendor-request-status rejected mb-2">Time conflict</div>
                  ) : candidate.can_fit ? (
                    <div className="vendor-request-status approved mb-2">Can transfer all bookings</div>
                  ) : (
                    <div className="vendor-request-status pending mb-2">Insufficient free seats</div>
                  )}
                  <div className="d-flex gap-2">
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-light"
                      disabled={!candidate.can_fit || swapRunning}
                      onClick={() => setSwapTargetHall(candidate.hall)}
                    >
                      Select
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm btn-primary"
                      disabled={!candidate.can_fit || swapRunning}
                      onClick={() => handleQuickSwap(candidate.hall)}
                    >
                      1-Click Swap
                    </button>
                  </div>
                </div>
              ))}
              {!hallSwapPreview?.candidates?.length ? (
                <div className="text-muted">No target halls available for swap.</div>
              ) : null}
            </div>
          ) : null}
        </div>
      </AdminModal>
    </div>
  );
}

function findMovieForShow(movies, show) {
  if (!Array.isArray(movies) || !show) return null;

  const showMovieId = String(show.movieId || show.movie_id || "");
  if (showMovieId) {
    const byId = movies.find((movie) => String(movie.id) === showMovieId);
    if (byId) return byId;
  }

  const showMovieTitle = String(show.movie || "").trim().toLowerCase();
  if (!showMovieTitle) return null;
  return (
    movies.find((movie) => String(movie.title || "").trim().toLowerCase() === showMovieTitle) ||
    null
  );
}

function useSafeAppContext() {
  try {
    return useAppContext?.();
  } catch {
    return null;
  }
}

function normalizeHallName(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function buildEmptyShow(movies, halls = []) {
  const firstMovie = (movies || [])[0];
  const firstHall = Array.isArray(halls) && halls.length ? halls[0] : "";
  const today = new Date().toISOString().slice(0, 10);
  return {
    movieId: firstMovie?.id || "",
    hall: firstHall,
    date: today,
    repeatDays: "1",
    slot: "Evening",
    start: "18:30",
    end: "20:30",
    screenType: "Standard",
    price: "450",
    status: "Open",
    listingStatus: "Now Showing",
  };
}

function buildEmptyMovie() {
  return {
    title: "",
    duration: "",
    genre: "",
    language: "",
    rating: "",
    releaseDate: "",
    status: "COMING_SOON",
    synopsis: "",
    posterFile: null,
    trailerUrl: "",
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
    const raw = sessionStorage.getItem("vendor") || localStorage.getItem("vendor");
    return JSON.parse(raw || "null");
  } catch {
    return null;
  }
}
