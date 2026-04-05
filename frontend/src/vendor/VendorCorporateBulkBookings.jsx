import { useEffect, useMemo, useState } from "react";
import { Building2, Download, FileSpreadsheet, HandCoins } from "lucide-react";
import {
  createVendorBulkTicketBatch,
  exportVendorBulkTicketBatch,
  fetchVendorBulkTicketBatches,
  fetchVendorPrivateScreeningRequests,
  fetchShows,
  updateVendorPrivateScreeningRequest,
} from "../lib/catalogApi";
import { getVendorSessionData } from "../lib/authSession";

const screeningActions = [
  "REVIEWED",
  "COUNTERED",
  "ACCEPTED",
  "REJECTED",
  "INVOICED",
  "COMPLETED",
];

export default function VendorCorporateBulkBookings() {
  const vendor = getVendorSessionData() || {};
  const vendorId = String(vendor?.id || "").trim();
  const [loading, setLoading] = useState(false);
  const [requests, setRequests] = useState([]);
  const [batches, setBatches] = useState([]);
  const [vendorShows, setVendorShows] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [updatingRequestId, setUpdatingRequestId] = useState(null);
  const [creatingBatch, setCreatingBatch] = useState(false);
  const [exportingBatchId, setExportingBatchId] = useState(null);
  const [selectedMovieKey, setSelectedMovieKey] = useState("");
  const [selectedShowId, setSelectedShowId] = useState("");
  const [actionState, setActionState] = useState({});
  const [batchForm, setBatchForm] = useState({
    corporate_name: "",
    contact_person: "",
    contact_email: "",
    movie_title: "",
    hall: "",
    show_date: "",
    show_time: "",
    valid_until: "",
    ticket_count: 50,
    unit_price: "0",
    notes: "",
  });

  const openRequestsCount = requests.filter(
    (item) => !["COMPLETED", "REJECTED"].includes(String(item.status || "").toUpperCase())
  ).length;
  const totalBatchTickets = batches.reduce((sum, item) => sum + Number(item.ticket_count || 0), 0);
  const totalBatchRevenue = batches.reduce((sum, item) => sum + Number(item.total_amount || 0), 0);
  const estimatedBatchAmount =
    Number(batchForm.ticket_count || 0) * Number(batchForm.unit_price || 0);
  const movieOptions = useMemo(() => {
    const optionMap = new Map();
    (Array.isArray(vendorShows) ? vendorShows : []).forEach((show) => {
      const movieTitle = String(show?.movie || "").trim();
      if (!movieTitle) return;
      const movieId = String(show?.movieId || "").trim();
      const key = movieId || `title:${movieTitle.toLowerCase()}`;
      if (optionMap.has(key)) return;
      optionMap.set(key, {
        key,
        movieId,
        title: movieTitle,
      });
    });
    return Array.from(optionMap.values()).sort((a, b) => a.title.localeCompare(b.title));
  }, [vendorShows]);

  const selectedMovie = useMemo(
    () => movieOptions.find((option) => option.key === selectedMovieKey) || null,
    [movieOptions, selectedMovieKey]
  );

  const movieShows = useMemo(() => {
    if (!selectedMovie) return [];
    return (Array.isArray(vendorShows) ? vendorShows : []).filter((show) => {
      const showMovieId = String(show?.movieId || "").trim();
      const showMovieTitle = String(show?.movie || "").trim();
      return selectedMovie.movieId
        ? showMovieId === selectedMovie.movieId
        : showMovieTitle.toLowerCase() === selectedMovie.title.toLowerCase();
    });
  }, [selectedMovie, vendorShows]);

  const availableMovieShows = useMemo(
    () =>
      movieShows
        .filter((show) => Boolean(show?.bookingOpen))
        .slice()
        .sort(sortShowsByDateTime),
    [movieShows]
  );

  const hallOptions = useMemo(() => {
    const hallSet = new Set();
    availableMovieShows.forEach((show) => {
      const hallName = String(show?.hall || "").trim();
      if (hallName) hallSet.add(hallName);
    });
    return Array.from(hallSet).sort((a, b) => a.localeCompare(b));
  }, [availableMovieShows]);

  const showSlotOptions = useMemo(() => {
    const selectedHall = String(batchForm.hall || "").trim().toLowerCase();
    return availableMovieShows.filter((show) => {
      if (!selectedHall) return true;
      return String(show?.hall || "").trim().toLowerCase() === selectedHall;
    });
  }, [availableMovieShows, batchForm.hall]);

  const selectedShow = useMemo(
    () => showSlotOptions.find((show) => String(show?.id || "") === String(selectedShowId || "")) || null,
    [showSlotOptions, selectedShowId]
  );

  const recommendedUnitPrice = useMemo(() => {
    if (selectedShow?.price != null && Number.isFinite(Number(selectedShow.price))) {
      return Number(selectedShow.price);
    }
    const pricedSlots = showSlotOptions
      .map((show) => Number(show?.price))
      .filter((value) => Number.isFinite(value) && value > 0);
    if (!pricedSlots.length) return null;
    return pricedSlots.reduce((sum, value) => sum + value, 0) / pricedSlots.length;
  }, [selectedShow, showSlotOptions]);

  const loadData = async () => {
    setLoading(true);
    setError("");
    try {
      const [privateRequests, ticketBatches, shows] = await Promise.all([
        fetchVendorPrivateScreeningRequests(),
        fetchVendorBulkTicketBatches(),
        fetchShows(vendorId ? { vendor_id: vendorId } : {}),
      ]);
      setRequests(Array.isArray(privateRequests) ? privateRequests : []);
      setBatches(Array.isArray(ticketBatches) ? ticketBatches : []);
      setVendorShows(Array.isArray(shows) ? shows : []);
    } catch (err) {
      setError(err.message || "Failed to load corporate booking data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [vendorId]);

  useEffect(() => {
    if (!movieOptions.length) {
      setSelectedMovieKey("");
      setSelectedShowId("");
      setBatchForm((prev) =>
        prev.movie_title || prev.hall || prev.show_date || prev.show_time
          ? {
              ...prev,
              movie_title: "",
              hall: "",
              show_date: "",
              show_time: "",
            }
          : prev
      );
      return;
    }

    const hasSelectedMovie = movieOptions.some((option) => option.key === selectedMovieKey);
    const nextSelectedMovie = hasSelectedMovie ? selectedMovieKey : movieOptions[0].key;
    if (nextSelectedMovie !== selectedMovieKey) {
      setSelectedMovieKey(nextSelectedMovie);
    }
  }, [movieOptions, selectedMovieKey]);

  useEffect(() => {
    if (!selectedMovie) {
      setBatchForm((prev) => (prev.movie_title ? { ...prev, movie_title: "" } : prev));
      return;
    }
    setBatchForm((prev) =>
      prev.movie_title === selectedMovie.title
        ? prev
        : { ...prev, movie_title: selectedMovie.title }
    );
  }, [selectedMovie]);

  useEffect(() => {
    if (!hallOptions.length) {
      setBatchForm((prev) => (prev.hall ? { ...prev, hall: "" } : prev));
      return;
    }
    if (hallOptions.includes(batchForm.hall)) return;
    setBatchForm((prev) => ({ ...prev, hall: hallOptions[0] }));
  }, [hallOptions, batchForm.hall]);

  useEffect(() => {
    if (!showSlotOptions.length) {
      if (selectedShowId) setSelectedShowId("");
      return;
    }
    const hasSelectedShow = showSlotOptions.some(
      (show) => String(show?.id || "") === String(selectedShowId || "")
    );
    if (!hasSelectedShow) {
      setSelectedShowId(String(showSlotOptions[0]?.id || ""));
    }
  }, [showSlotOptions, selectedShowId]);

  useEffect(() => {
    if (!selectedShow) return;
    setBatchForm((prev) => {
      const next = { ...prev };
      let changed = false;

      const nextHall = String(selectedShow?.hall || "").trim();
      if (nextHall && next.hall !== nextHall) {
        next.hall = nextHall;
        changed = true;
      }

      const nextDate = String(selectedShow?.date || "").trim();
      if (nextDate && next.show_date !== nextDate) {
        next.show_date = nextDate;
        changed = true;
      }

      const nextTime = String(selectedShow?.start || "").trim();
      if (nextTime && next.show_time !== nextTime) {
        next.show_time = nextTime;
        changed = true;
      }

      if (selectedShow?.price != null && Number.isFinite(Number(selectedShow.price))) {
        const nextPrice = Number(selectedShow.price).toFixed(2);
        if (String(next.unit_price || "") !== nextPrice) {
          next.unit_price = nextPrice;
          changed = true;
        }
      }

      return changed ? next : prev;
    });
  }, [selectedShow]);

  const handleRequestAction = async (requestItem) => {
    const current = actionState[requestItem.id] || {};
    if (!current.status) {
      setError("Choose an action status first.");
      return;
    }

    setUpdatingRequestId(requestItem.id);
    setError("");
    setNotice("");
    try {
      await updateVendorPrivateScreeningRequest(requestItem.id, {
        status: current.status,
        quoted_amount: current.quoted_amount,
        counter_offer_amount: current.counter_offer_amount,
        invoice_number: current.invoice_number,
        vendor_notes: current.vendor_notes,
        invoice_notes: current.invoice_notes,
      });
      setNotice(`Request #${requestItem.id} updated.`);
      await loadData();
    } catch (err) {
      setError(err.message || "Failed to update screening request.");
    } finally {
      setUpdatingRequestId(null);
    }
  };

  const handleCreateBatch = async (event) => {
    event.preventDefault();
    setError("");
    setNotice("");
    if (!String(batchForm.corporate_name || "").trim()) {
      setError("Corporate name is required.");
      return;
    }
    if (!String(batchForm.movie_title || "").trim()) {
      setError("Choose a movie from your added shows.");
      return;
    }
    if (!String(batchForm.hall || "").trim()) {
      setError("Choose a hall for the selected movie.");
      return;
    }
    if (!showSlotOptions.length) {
      setError("No booking-open show slots are available for this movie/hall.");
      return;
    }
    if (!selectedShow) {
      setError("Choose an available show slot before generating a bulk batch.");
      return;
    }
    if (Number(batchForm.ticket_count || 0) < 1) {
      setError("Ticket count must be at least 1.");
      return;
    }
    if (
      String(batchForm.contact_email || "").trim() &&
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(batchForm.contact_email || "").trim())
    ) {
      setError("Enter a valid contact email.");
      return;
    }
    if (
      String(batchForm.show_date || "").trim() &&
      String(batchForm.valid_until || "").trim() &&
      String(batchForm.valid_until).trim() < String(batchForm.show_date).trim()
    ) {
      setError("Valid until date cannot be earlier than show date.");
      return;
    }

    setCreatingBatch(true);
    try {
      await createVendorBulkTicketBatch({
        ...batchForm,
        show_id: selectedShow?.id,
        ticket_count: Number(batchForm.ticket_count || 0),
        unit_price: Number(batchForm.unit_price || 0),
      });
      setNotice("Bulk ticket batch generated.");
      setBatchForm((prev) => ({
        ...prev,
        corporate_name: "",
        contact_person: "",
        contact_email: "",
        notes: "",
      }));
      await loadData();
    } catch (err) {
      setError(err.message || "Failed to create bulk ticket batch.");
    } finally {
      setCreatingBatch(false);
    }
  };

  const handleExport = async (batch) => {
    setExportingBatchId(batch.id);
    setError("");
    setNotice("");
    try {
      const { blob, filename } = await exportVendorBulkTicketBatch(batch.id);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      setNotice(`Exported ${filename}`);
      await loadData();
    } catch (err) {
      setError(err.message || "Failed to export bulk tickets.");
    } finally {
      setExportingBatchId(null);
    }
  };

  return (
    <div className="vendor-dashboard">
      <div className="vendor-marketing-hero mb-3">
        <div>
          <p className="vendor-marketing-eyebrow mb-1">Enterprise Bookings</p>
          <h2 className="mb-1">Corporate & Bulk Bookings</h2>
          <p className="text-muted mb-0">
            Manage private screening requests and export high-volume ticket batches with confidence.
          </p>
        </div>
        <div className="vendor-marketing-metrics">
          <div className="vendor-marketing-metric">
            <span>Open Requests</span>
            <strong>{openRequestsCount}</strong>
          </div>
          <div className="vendor-marketing-metric">
            <span>Batch Tickets</span>
            <strong>{totalBatchTickets}</strong>
          </div>
          <div className="vendor-marketing-metric">
            <span>Batch Revenue</span>
            <strong>NPR {totalBatchRevenue.toFixed(0)}</strong>
          </div>
        </div>
      </div>

      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3 mb-3">
        <div>
          <p className="vendor-breadcrumb mb-0">
            <span>Operations</span>
            <span className="vendor-dot">&#8226;</span>
            <span>Corporate & Bulk</span>
          </p>
        </div>
      </div>

      {error ? <div className="alert alert-danger">{error}</div> : null}
      {notice ? <div className="alert alert-success">{notice}</div> : null}

      <section className="vendor-card mb-3">
        <div className="vendor-card-header">
          <div>
            <h3>
              <Building2 size={18} className="me-2" />
              Private Screening Requests
            </h3>
            <p>Review incoming requests, counter-offer, and finalize invoices.</p>
          </div>
        </div>

        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Organization</th>
                <th>Contact</th>
                <th>Date & Time</th>
                <th>Attendees</th>
                <th>Status</th>
                <th>Vendor Action</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((item) => {
                const action = actionState[item.id] || {};
                return (
                  <tr key={item.id}>
                    <td>
                      <div className="fw-semibold">{item.organization_name}</div>
                      <small className="text-muted">Movie: {item.preferred_movie_title || "Any"}</small>
                    </td>
                    <td>
                      <div>{item.contact_person}</div>
                      <small>{item.contact_email}</small>
                    </td>
                    <td>
                      <div>{item.preferred_date || "-"}</div>
                      <small>{item.preferred_start_time || "-"}</small>
                    </td>
                    <td>{item.attendee_count || 0}</td>
                    <td>
                      <span className={`vendor-request-status ${getRequestStatusClass(item.status)}`}>
                        {item.status}
                      </span>
                    </td>
                    <td style={{ minWidth: 340 }}>
                      <div className="d-flex flex-wrap gap-2 align-items-center">
                        <select
                          className="form-select form-select-sm"
                          style={{ maxWidth: 150 }}
                          value={action.status || ""}
                          onChange={(event) =>
                            setActionState((prev) => ({
                              ...prev,
                              [item.id]: { ...action, status: event.target.value },
                            }))
                          }
                        >
                          <option value="">Action</option>
                          {screeningActions.map((statusValue) => (
                            <option key={statusValue} value={statusValue}>
                              {statusValue}
                            </option>
                          ))}
                        </select>
                        <input
                          className="form-control form-control-sm"
                          placeholder="Quote"
                          style={{ maxWidth: 90 }}
                          value={action.quoted_amount || ""}
                          onChange={(event) =>
                            setActionState((prev) => ({
                              ...prev,
                              [item.id]: { ...action, quoted_amount: event.target.value },
                            }))
                          }
                        />
                        <input
                          className="form-control form-control-sm"
                          placeholder="Counter"
                          style={{ maxWidth: 95 }}
                          value={action.counter_offer_amount || ""}
                          onChange={(event) =>
                            setActionState((prev) => ({
                              ...prev,
                              [item.id]: { ...action, counter_offer_amount: event.target.value },
                            }))
                          }
                        />
                        <input
                          className="form-control form-control-sm"
                          placeholder="Invoice #"
                          style={{ maxWidth: 110 }}
                          value={action.invoice_number || ""}
                          onChange={(event) =>
                            setActionState((prev) => ({
                              ...prev,
                              [item.id]: { ...action, invoice_number: event.target.value },
                            }))
                          }
                        />
                        <button
                          type="button"
                          className="btn btn-sm btn-primary"
                          onClick={() => handleRequestAction(item)}
                          disabled={updatingRequestId === item.id}
                        >
                          <HandCoins size={14} className="me-1" />
                          {updatingRequestId === item.id ? "Saving" : "Update"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {!loading && requests.length === 0 ? (
                <tr>
                  <td colSpan="6">No private screening requests assigned yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="vendor-card mb-3">
        <div className="vendor-card-header">
          <div>
            <h3>
              <FileSpreadsheet size={18} className="me-2" />
              Generate Bulk Ticket Batch
            </h3>
            <p>Create hundreds of valid ticket references and export CSV instantly.</p>
          </div>
        </div>

        <form className="row g-3" onSubmit={handleCreateBatch}>
          <div className="col-md-6 col-xl-4">
            <label className="form-label mb-1" htmlFor="bulk-corporate-name">
              Corporate name <span className="text-danger">*</span>
            </label>
            <input
              id="bulk-corporate-name"
              className="form-control"
              placeholder="e.g. Nabil Bank Ltd."
              value={batchForm.corporate_name}
              required
              onChange={(event) =>
                setBatchForm((prev) => ({ ...prev, corporate_name: event.target.value }))
              }
            />
          </div>

          <div className="col-md-6 col-xl-3">
            <label className="form-label mb-1" htmlFor="bulk-contact-person">
              Contact person
            </label>
            <input
              id="bulk-contact-person"
              className="form-control"
              placeholder="e.g. Ashim Sharma"
              value={batchForm.contact_person}
              onChange={(event) =>
                setBatchForm((prev) => ({ ...prev, contact_person: event.target.value }))
              }
            />
          </div>

          <div className="col-md-6 col-xl-3">
            <label className="form-label mb-1" htmlFor="bulk-contact-email">
              Contact email
            </label>
            <input
              id="bulk-contact-email"
              className="form-control"
              type="email"
              placeholder="name@company.com"
              value={batchForm.contact_email}
              onChange={(event) =>
                setBatchForm((prev) => ({ ...prev, contact_email: event.target.value }))
              }
            />
          </div>

          <div className="col-md-6 col-xl-4">
            <label className="form-label mb-1" htmlFor="bulk-movie-title">
              Movie title
            </label>
            <select
              id="bulk-movie-title"
              className="form-select"
              value={selectedMovieKey}
              disabled={!movieOptions.length}
              onChange={(event) => {
                const nextKey = event.target.value;
                setSelectedMovieKey(nextKey);
              }}
            >
              {!movieOptions.length ? (
                <option value="">No added movies found</option>
              ) : null}
              {movieOptions.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.title}
                </option>
              ))}
            </select>
          </div>

          <div className="col-md-6 col-xl-3">
            <label className="form-label mb-1" htmlFor="bulk-hall">
              Hall
            </label>
            <select
              id="bulk-hall"
              className="form-select"
              value={batchForm.hall}
              disabled={!hallOptions.length}
              onChange={(event) =>
                setBatchForm((prev) => ({ ...prev, hall: event.target.value }))
              }
            >
              {!hallOptions.length ? (
                <option value="">No available hall for selected movie</option>
              ) : null}
              {hallOptions.map((hallName) => (
                <option key={hallName} value={hallName}>
                  {hallName}
                </option>
              ))}
            </select>
            <small className="text-muted d-block mt-1">
              Showing halls with booking-open slots only.
            </small>
          </div>

          <div className="col-md-6 col-xl-5">
            <label className="form-label mb-1" htmlFor="bulk-show-slot">
              Available show slot
            </label>
            <select
              id="bulk-show-slot"
              className="form-select"
              value={selectedShowId}
              disabled={!showSlotOptions.length}
              onChange={(event) => setSelectedShowId(event.target.value)}
            >
              {!showSlotOptions.length ? (
                <option value="">No booking-open slot available</option>
              ) : null}
              {showSlotOptions.map((show) => (
                <option key={show.id} value={String(show.id)}>
                  {buildShowSlotLabel(show)}
                </option>
              ))}
            </select>
            <small className="text-muted d-block mt-1">
              Select a slot to auto-fill hall, date, time, and price.
            </small>
          </div>

          <div className="col-md-4 col-xl-2">
            <label className="form-label mb-1" htmlFor="bulk-ticket-count">
              Ticket count
            </label>
            <input
              id="bulk-ticket-count"
              className="form-control"
              type="number"
              min="1"
              max="2000"
              placeholder="50"
              value={batchForm.ticket_count}
              onChange={(event) =>
                setBatchForm((prev) => ({ ...prev, ticket_count: event.target.value }))
              }
            />
          </div>

          <div className="col-md-4 col-xl-2">
            <label className="form-label mb-1" htmlFor="bulk-unit-price">
              Unit price (NPR)
            </label>
            <input
              id="bulk-unit-price"
              className="form-control"
              type="number"
              min="0"
              step="0.01"
              placeholder="200"
              value={batchForm.unit_price}
              onChange={(event) =>
                setBatchForm((prev) => ({ ...prev, unit_price: event.target.value }))
              }
            />
          </div>

          <div className="col-md-4 col-xl-2">
            <label className="form-label mb-1" htmlFor="bulk-show-date">
              Show date
            </label>
            <input
              id="bulk-show-date"
              className="form-control"
              type="date"
              value={batchForm.show_date}
              onChange={(event) =>
                setBatchForm((prev) => ({ ...prev, show_date: event.target.value }))
              }
            />
          </div>

          <div className="col-md-4 col-xl-2">
            <label className="form-label mb-1" htmlFor="bulk-show-time">
              Show time
            </label>
            <input
              id="bulk-show-time"
              className="form-control"
              type="time"
              value={batchForm.show_time}
              onChange={(event) =>
                setBatchForm((prev) => ({ ...prev, show_time: event.target.value }))
              }
            />
          </div>

          <div className="col-md-4 col-xl-2">
            <label className="form-label mb-1" htmlFor="bulk-valid-until">
              Valid until
            </label>
            <input
              id="bulk-valid-until"
              className="form-control"
              type="date"
              value={batchForm.valid_until}
              onChange={(event) =>
                setBatchForm((prev) => ({ ...prev, valid_until: event.target.value }))
              }
            />
          </div>

          <div className="col-12">
            <div className="vendor-corporate-detail-panel">
              <div className="vendor-corporate-detail-header">
                <h4>Corporate Booking Details</h4>
                <span
                  className={`vendor-corporate-detail-badge ${
                    showSlotOptions.length ? "" : "empty"
                  }`}
                >
                  {showSlotOptions.length
                    ? `${showSlotOptions.length} slot(s) open`
                    : "No open slot"}
                </span>
              </div>
              <div className="vendor-corporate-detail-grid">
                <div className="vendor-corporate-detail-item">
                  <span>Movie</span>
                  <strong>{batchForm.movie_title || "-"}</strong>
                </div>
                <div className="vendor-corporate-detail-item">
                  <span>Hall</span>
                  <strong>{batchForm.hall || "-"}</strong>
                </div>
                <div className="vendor-corporate-detail-item">
                  <span>Show Date</span>
                  <strong>{batchForm.show_date || "-"}</strong>
                </div>
                <div className="vendor-corporate-detail-item">
                  <span>Show Time</span>
                  <strong>{batchForm.show_time || "-"}</strong>
                </div>
                <div className="vendor-corporate-detail-item">
                  <span>Recommended Price</span>
                  <strong>{formatCurrency(recommendedUnitPrice)}</strong>
                </div>
                <div className="vendor-corporate-detail-item">
                  <span>Chosen Unit Price</span>
                  <strong>{formatCurrency(batchForm.unit_price)}</strong>
                </div>
                <div className="vendor-corporate-detail-item">
                  <span>Ticket Count</span>
                  <strong>{Number(batchForm.ticket_count || 0)}</strong>
                </div>
                <div className="vendor-corporate-detail-item">
                  <span>Estimated Total</span>
                  <strong>{formatCurrency(estimatedBatchAmount)}</strong>
                </div>
              </div>
            </div>
          </div>

          <div className="col-12">
            <label className="form-label mb-1" htmlFor="bulk-notes">
              Notes
            </label>
            <textarea
              id="bulk-notes"
              className="form-control"
              rows="2"
              placeholder="Optional notes for this corporate batch"
              value={batchForm.notes}
              onChange={(event) => setBatchForm((prev) => ({ ...prev, notes: event.target.value }))}
            />
          </div>

          <div className="col-12 d-flex flex-wrap justify-content-between align-items-center gap-2">
            <small className="text-muted">
              Estimated total: <strong>NPR {Number(estimatedBatchAmount || 0).toFixed(2)}</strong>
            </small>
            <button type="submit" className="btn btn-primary" disabled={creatingBatch}>
              {creatingBatch ? "Generating..." : "Generate Batch"}
            </button>
          </div>
        </form>
      </section>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Bulk Ticket Batches</h3>
            <p>Export ticket references and QR-ready links for corporate distribution.</p>
          </div>
        </div>

        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Corporate</th>
                <th>Movie / Hall</th>
                <th>Qty</th>
                <th>Total</th>
                <th>Status</th>
                <th>Created</th>
                <th>Export</th>
              </tr>
            </thead>
            <tbody>
              {batches.map((batch) => (
                <tr key={batch.id}>
                  <td>
                    <div className="fw-semibold">{batch.corporate_name}</div>
                    <small>{batch.contact_person || "-"}</small>
                  </td>
                  <td>
                    <div>{batch.movie_title || "Corporate Ticket"}</div>
                    <small>{batch.hall || "Private Hall"}</small>
                  </td>
                  <td>{batch.ticket_count || 0}</td>
                  <td>NPR {Number(batch.total_amount || 0).toFixed(2)}</td>
                  <td>
                    <span className={`vendor-request-status ${getRequestStatusClass(batch.status)}`}>
                      {batch.status}
                    </span>
                  </td>
                  <td>{formatDate(batch.created_at)}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-light"
                      onClick={() => handleExport(batch)}
                      disabled={exportingBatchId === batch.id}
                    >
                      <Download size={14} className="me-1" />
                      {exportingBatchId === batch.id ? "Exporting" : "Export CSV"}
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && batches.length === 0 ? (
                <tr>
                  <td colSpan="7">No bulk batches created yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleDateString();
}

function sortShowsByDateTime(a, b) {
  const left = toShowSortTime(a);
  const right = toShowSortTime(b);
  if (left === right) {
    const leftHall = String(a?.hall || "");
    const rightHall = String(b?.hall || "");
    return leftHall.localeCompare(rightHall);
  }
  return left - right;
}

function toShowSortTime(show) {
  const dateValue = String(show?.date || "").trim();
  const timeValue = String(show?.start || "00:00").trim() || "00:00";
  if (!dateValue) return Number.MAX_SAFE_INTEGER;
  const parsed = new Date(`${dateValue}T${timeValue}:00`);
  const stamp = parsed.getTime();
  return Number.isFinite(stamp) ? stamp : Number.MAX_SAFE_INTEGER;
}

function buildShowSlotLabel(show) {
  const dateLabel = String(show?.date || "Date TBD").trim() || "Date TBD";
  const timeLabel = String(show?.start || "--:--").trim() || "--:--";
  const hallLabel = String(show?.hall || "Hall").trim() || "Hall";
  const screenType = String(show?.screenType || "").trim();
  const price = Number(show?.price);
  const priceLabel = Number.isFinite(price) ? `NPR ${price.toFixed(2)}` : "Price not set";
  const screenSuffix = screenType ? ` | ${screenType}` : "";
  return `${dateLabel} | ${timeLabel} | ${hallLabel}${screenSuffix} | ${priceLabel}`;
}

function formatCurrency(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "NPR 0.00";
  return `NPR ${amount.toFixed(2)}`;
}

function getRequestStatusClass(value) {
  const status = String(value || "").trim().toUpperCase();
  if (["ACCEPTED", "COMPLETED", "INVOICED"].includes(status)) return "approved";
  if (["COUNTERED", "REVIEWED"].includes(status)) return "pending";
  if (["REJECTED", "CANCELLED"].includes(status)) return "rejected";
  return "neutral";
}
