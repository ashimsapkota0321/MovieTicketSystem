import { useEffect, useMemo, useState } from "react";
import {
  fetchVendorSeatLayout,
  saveVendorSeatLayout,
  updateVendorSeatStatus,
} from "../lib/catalogApi";
import { useAppContext } from "../context/Appcontext";

const CATEGORY_KEYS = ["normal", "executive", "premium", "vip"];

export default function VendorSeats() {
  const ctx = safeUseAppContext();
  const shows = ctx?.showtimes ?? [];
  const vendor = getStoredVendor();
  const vendorId = vendor?.id;
  const vendorName = vendor?.name || vendor?.username || "Vendor";

  const vendorShows = useMemo(() => {
    if (!Array.isArray(shows)) return [];
    return shows.filter((show) => {
      if (vendorId && String(show.vendorId) === String(vendorId)) return true;
      const vendorLabel = String(show.vendor || "").trim().toLowerCase();
      return vendorLabel && vendorLabel === String(vendorName).trim().toLowerCase();
    });
  }, [shows, vendorId, vendorName]);

  const [selectedShowId, setSelectedShowId] = useState("");
  const [selectedHall, setSelectedHall] = useState("Hall A");
  const [layout, setLayout] = useState(null);
  const [loading, setLoading] = useState(false);
  const [savingLayout, setSavingLayout] = useState(false);
  const [updatingSeat, setUpdatingSeat] = useState("");
  const [statusMode, setStatusMode] = useState("Unavailable");
  const [message, setMessage] = useState("");
  const [rows, setRows] = useState(10);
  const [columns, setColumns] = useState(15);
  const [categoryRows, setCategoryRows] = useState({
    normal: 3,
    executive: 3,
    premium: 2,
    vip: 2,
  });

  useEffect(() => {
    if (!vendorShows.length) return;
    if (selectedShowId) return;
    setSelectedShowId(String(vendorShows[0].id));
  }, [vendorShows, selectedShowId]);

  useEffect(() => {
    if (!vendorId) return;
    let active = true;
    const loadLayout = async () => {
      setLoading(true);
      setMessage("");
      try {
        const params = { vendor_id: vendorId };
        if (selectedShowId) params.show_id = selectedShowId;
        if (selectedHall) params.hall = selectedHall;
        const data = await fetchVendorSeatLayout(params);
        if (!active) return;

        setLayout(data);
        if (data?.hall) setSelectedHall(data.hall);
        if (Number.isInteger(data?.total_rows) && data.total_rows > 0) {
          setRows(data.total_rows);
        }
        if (Number.isInteger(data?.total_columns) && data.total_columns > 0) {
          setColumns(data.total_columns);
        }
        const inferred = inferCategoryRows(data?.seat_groups || []);
        if (Object.values(inferred).some((value) => value > 0)) {
          setCategoryRows(inferred);
        }
      } catch (error) {
        if (!active) return;
        setLayout(null);
        setMessage(error.message || "Failed to load seat layout.");
      } finally {
        if (active) setLoading(false);
      }
    };

    loadLayout();
    return () => {
      active = false;
    };
  }, [vendorId, selectedShowId, selectedHall]);

  const handleSaveLayout = async () => {
    if (!vendorId) return;
    setSavingLayout(true);
    setMessage("");
    try {
      const payload = {
        vendor_id: vendorId,
        show_id: selectedShowId || undefined,
        hall: selectedHall || "Hall A",
        rows: Number(rows) || 10,
        columns: Number(columns) || 15,
        category_rows: {
          normal: Number(categoryRows.normal) || 0,
          executive: Number(categoryRows.executive) || 0,
          premium: Number(categoryRows.premium) || 0,
          vip: Number(categoryRows.vip) || 0,
        },
      };
      const data = await saveVendorSeatLayout(payload);
      setLayout(data);
      setMessage(data?.message || "Seat layout saved.");
    } catch (error) {
      setMessage(error.message || "Failed to save seat layout.");
    } finally {
      setSavingLayout(false);
    }
  };

  const handleSeatToggle = async (seat) => {
    if (!seat || !seat.label) return;
    if (!vendorId || !selectedShowId) {
      setMessage("Select a show to update seat availability.");
      return;
    }
    if (String(seat.status).toLowerCase() === "booked") return;

    const targetStatus = statusMode === "Unavailable" ? "Unavailable" : "Available";
    const currentStatus = String(seat.status || "").toLowerCase();
    if (
      (targetStatus === "Unavailable" && currentStatus === "unavailable") ||
      (targetStatus === "Available" && currentStatus === "available")
    ) {
      return;
    }

    setUpdatingSeat(seat.label);
    setMessage("");
    try {
      const data = await updateVendorSeatStatus({
        vendor_id: vendorId,
        show_id: selectedShowId,
        hall: selectedHall,
        status: targetStatus,
        seat_labels: [seat.label],
      });
      setLayout(data);
      setMessage(data?.message || "Seat updated.");
    } catch (error) {
      setMessage(error.message || "Failed to update seat.");
    } finally {
      setUpdatingSeat("");
    }
  };

  const { rowLabels, seatColumns, seatMap } = useMemo(
    () => buildSeatGrid(layout),
    [layout]
  );

  return (
    <div className="vendor-dashboard">
      <div>
        <h2 className="mb-1">Seat Management</h2>
        <p className="text-muted mb-0">
          Configure hall layout, seat categories, and per-show seat availability.
        </p>
      </div>
      <div className="vendor-breadcrumb">
        <span>Seats</span>
        <span className="vendor-dot">&#8226;</span>
        <span>Layouts & Availability</span>
      </div>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Layout Configuration</h3>
            <p>Create realistic category sections per hall.</p>
          </div>
        </div>
        <div className="row g-3">
          <div className="col-md-4">
            <label className="form-label">Show</label>
            <select
              className="form-select"
              value={selectedShowId}
              onChange={(event) => {
                const value = event.target.value;
                setSelectedShowId(value);
                const selectedShow = vendorShows.find(
                  (show) => String(show.id) === String(value)
                );
                if (selectedShow?.hall) setSelectedHall(selectedShow.hall);
              }}
            >
              <option value="">Select Show</option>
              {vendorShows.map((show) => (
                <option key={show.id} value={show.id}>
                  {show.movie} | {show.date} {show.start}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-4">
            <label className="form-label">Hall</label>
            <input
              className="form-control"
              value={selectedHall}
              onChange={(event) => setSelectedHall(event.target.value)}
            />
          </div>
          <div className="col-md-2">
            <label className="form-label">Rows</label>
            <input
              type="number"
              min="1"
              max="52"
              className="form-control"
              value={rows}
              onChange={(event) => setRows(event.target.value)}
            />
          </div>
          <div className="col-md-2">
            <label className="form-label">Columns</label>
            <input
              type="number"
              min="1"
              max="40"
              className="form-control"
              value={columns}
              onChange={(event) => setColumns(event.target.value)}
            />
          </div>
          {CATEGORY_KEYS.map((key) => (
            <div className="col-md-3" key={key}>
              <label className="form-label">{capitalize(key)} Rows</label>
              <input
                type="number"
                min="0"
                max="52"
                className="form-control"
                value={categoryRows[key]}
                onChange={(event) =>
                  setCategoryRows((prev) => ({
                    ...prev,
                    [key]: event.target.value,
                  }))
                }
              />
            </div>
          ))}
        </div>

        <div className="vendor-seatActions">
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleSaveLayout}
            disabled={savingLayout}
          >
            {savingLayout ? "Saving..." : "Save Layout"}
          </button>
        </div>
      </section>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Seat Availability</h3>
            <p>Booked seats are locked. Toggle available/unavailable for maintenance.</p>
          </div>
          <div className="vendor-seatMode">
            <label className="form-label mb-0">Click Action</label>
            <select
              className="form-select"
              value={statusMode}
              onChange={(event) => setStatusMode(event.target.value)}
            >
              <option>Unavailable</option>
              <option>Available</option>
            </select>
          </div>
        </div>

        <div className="vendor-seatLegend">
          <span><i className="dot normal" /> Normal</span>
          <span><i className="dot executive" /> Executive</span>
          <span><i className="dot premium" /> Premium</span>
          <span><i className="dot vip" /> VIP</span>
          <span><i className="dot booked" /> Booked</span>
          <span><i className="dot unavailable" /> Unavailable</span>
        </div>

        <div className="vendor-seatCanvas">
          <div className="vendor-screen">SCREEN</div>
          {loading ? (
            <div className="text-muted">Loading layout...</div>
          ) : (
            <div className="vendor-seatGrid">
              {rowLabels.map((rowLabel) => (
                <div className="vendor-seatRow" key={rowLabel}>
                  <div className="vendor-seatRowLabel">{rowLabel}</div>
                  <div className="vendor-seatRowCells">
                    {seatColumns.map((col) => {
                      const label = `${rowLabel}${col}`;
                      const seat = seatMap.get(label) || null;
                      const seatType = normalizeSeatType(seat?.seat_type);
                      const seatStatus = String(seat?.status || "available").toLowerCase();
                      const isBooked = seatStatus === "booked";
                      const isUnavailable = seatStatus === "unavailable";
                      const className = `vendor-seatCell ${seatType} ${
                        isBooked ? "booked" : isUnavailable ? "unavailable" : ""
                      }`;
                      return (
                        <button
                          key={label}
                          type="button"
                          className={className}
                          disabled={isBooked || updatingSeat === label}
                          onClick={() => handleSeatToggle(seat || { label, seat_type: seatType })}
                          title={label}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
              {!rowLabels.length ? (
                <div className="text-muted">No seat layout found for this hall.</div>
              ) : null}
            </div>
          )}
        </div>
      </section>

      {message ? <div className="vendor-seatMessage">{message}</div> : null}
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

function inferCategoryRows(groups) {
  const output = { normal: 0, executive: 0, premium: 0, vip: 0 };
  if (!Array.isArray(groups)) return output;
  groups.forEach((group) => {
    const key = String(group?.key || "").toLowerCase();
    if (!Object.prototype.hasOwnProperty.call(output, key)) return;
    output[key] = Array.isArray(group?.rows) ? group.rows.length : 0;
  });
  return output;
}

function buildSeatGrid(layout) {
  const seats = Array.isArray(layout?.seats) ? layout.seats : [];
  const rowLabels = Array.from(
    new Set(
      seats
        .map((seat) => String(seat.row_label || "").trim().toUpperCase())
        .filter(Boolean)
    )
  ).sort(sortRowLabels);

  const seatColumns = Array.from(
    new Set(
      seats
        .map((seat) => Number(seat.seat_number))
        .filter((value) => Number.isInteger(value) && value > 0)
    )
  ).sort((a, b) => a - b);

  const seatMap = new Map();
  seats.forEach((seat) => {
    const row = String(seat.row_label || "").trim().toUpperCase();
    const column = String(seat.seat_number || "").trim();
    if (!row || !column) return;
    seatMap.set(`${row}${column}`, seat);
  });

  return { rowLabels, seatColumns, seatMap };
}

function sortRowLabels(a, b) {
  return rowScore(a) - rowScore(b);
}

function rowScore(value) {
  return String(value || "")
    .toUpperCase()
    .split("")
    .reduce((score, char) => score * 26 + (char.charCodeAt(0) - 64), 0);
}

function normalizeSeatType(value) {
  const text = String(value || "").toLowerCase();
  if (text.includes("vip")) return "vip";
  if (text.includes("prem")) return "premium";
  if (text.includes("exec")) return "executive";
  return "normal";
}

function capitalize(value) {
  const text = String(value || "");
  if (!text) return text;
  return text.charAt(0).toUpperCase() + text.slice(1);
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

