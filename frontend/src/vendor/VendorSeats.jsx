import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import "../css/seatSelection.css";
import {
  fetchVendorSeatLayout,
  saveVendorSeatLayout,
  updateVendorSeatStatus,
} from "../lib/catalogApi";
import { useAppContext } from "../context/Appcontext";

const CATEGORY_KEYS = ["normal", "executive", "premium", "vip"];
const defaultSeatGroups = [
  { key: "normal", label: "Normal", rows: ["A", "B", "C", "D"] },
  { key: "executive", label: "Executive", rows: ["E", "F", "G", "H"] },
  { key: "premium", label: "Premium", rows: ["I", "J"] },
  { key: "vip", label: "VIP", rows: ["K", "L"] },
];
const defaultSeatCols = Array.from({ length: 15 }, (_, i) => i + 1);

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
  const [soldSeatSet, setSoldSeatSet] = useState(() => new Set());
  const [unavailableSeatSet, setUnavailableSeatSet] = useState(() => new Set());
  const [reservedSeatSet, setReservedSeatSet] = useState(() => new Set());
  const [dynamicSeatGroups, setDynamicSeatGroups] = useState(defaultSeatGroups);
  const [dynamicSeatCols, setDynamicSeatCols] = useState(defaultSeatCols);
  const [categoryRows, setCategoryRows] = useState({
    normal: 3,
    executive: 3,
    premium: 2,
    vip: 2,
  });
  const [layoutDirty, setLayoutDirty] = useState(false);
  const layoutDirtyRef = useRef(false);

  useEffect(() => {
    layoutDirtyRef.current = layoutDirty;
  }, [layoutDirty]);

  const seatMapStyle = useMemo(() => {
    const colCount = dynamicSeatCols.length || Number(layout?.total_columns) || 0;
    const inferredRowCount = Array.isArray(dynamicSeatGroups)
      ? dynamicSeatGroups.reduce(
          (sum, group) => sum + (Array.isArray(group?.rows) ? group.rows.length : 0),
          0
        )
      : 0;
    const rowCount = Number(layout?.total_rows) || inferredRowCount || 0;

    let seatSize = 42;
    let seatGap = 10;

    if (colCount > 15) {
      seatSize = 38;
      seatGap = 9;
    }
    if (colCount > 18) {
      seatSize = 34;
      seatGap = 8;
    }
    if (colCount > 21) {
      seatSize = 30;
      seatGap = 7;
    }
    if (colCount > 26) {
      seatSize = 26;
      seatGap = 6;
    }
    if (colCount > 32) {
      seatSize = 22;
      seatGap = 5;
    }

    if (rowCount > 18) {
      seatSize = Math.min(seatSize, 30);
      seatGap = Math.min(seatGap, 7);
    }
    if (rowCount > 24) {
      seatSize = Math.min(seatSize, 26);
      seatGap = Math.min(seatGap, 6);
    }

    return {
      "--seat-count": dynamicSeatCols.length,
      "--seat-size": `${seatSize}px`,
      "--seat-gap": `${seatGap}px`,
    };
  }, [dynamicSeatCols.length, dynamicSeatGroups, layout?.total_columns, layout?.total_rows]);

  const applyLayoutData = (data, options = {}) => {
    const forceConfig = Boolean(options.forceConfig);
    const canUpdateConfig = forceConfig || !layoutDirtyRef.current;

    setLayout(data);
    if (canUpdateConfig) {
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
    }

    const groups =
      Array.isArray(data?.seat_groups) && data.seat_groups.length
        ? data.seat_groups
        : defaultSeatGroups;
    const columns =
      Array.isArray(data?.seat_columns) && data.seat_columns.length
        ? data.seat_columns
            .map((value) => Number(value))
            .filter((value) => Number.isInteger(value) && value > 0)
        : defaultSeatCols;
    const seatItems = Array.isArray(data?.seats) ? data.seats : [];
    const soldSeats = Array.isArray(data?.sold_seats) ? data.sold_seats : [];
    const unavailableSeats = Array.isArray(data?.unavailable_seats)
      ? data.unavailable_seats
      : [];
    const reservedSeats = Array.isArray(data?.reserved_seats)
      ? data.reserved_seats
      : Array.isArray(data?.reservedSeats)
        ? data.reservedSeats
        : [];
    const soldFromSeats = seatItems
      .filter((seat) => String(seat?.status || "").toLowerCase() === "booked")
      .map((seat) => seat.label);
    const unavailableFromSeats = seatItems
      .filter((seat) => String(seat?.status || "").toLowerCase() === "unavailable")
      .map((seat) => seat.label);
    const nextSoldSet = new Set(
      [...soldSeats, ...soldFromSeats]
        .map((seat) => normalizeSeatLabel(seat))
        .filter(Boolean)
    );
    const nextUnavailableSet = new Set(
      [...unavailableSeats, ...unavailableFromSeats]
        .map((seat) => normalizeSeatLabel(seat))
        .filter(Boolean)
    );
    const nextReservedSet = new Set(
      reservedSeats.map((seat) => normalizeSeatLabel(seat)).filter(Boolean)
    );

    setDynamicSeatGroups(groups);
    setDynamicSeatCols(columns.length ? columns : defaultSeatCols);
    setSoldSeatSet(nextSoldSet);
    setUnavailableSeatSet(nextUnavailableSet);
    setReservedSeatSet(nextReservedSet);
  };

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

        applyLayoutData(data);
      } catch (error) {
        if (!active) return;
        setLayout(null);
        setMessage(error.message || "Failed to load seat layout.");
        setSoldSeatSet(new Set());
        setUnavailableSeatSet(new Set());
        setReservedSeatSet(new Set());
        setDynamicSeatGroups(defaultSeatGroups);
        setDynamicSeatCols(defaultSeatCols);
      } finally {
        if (active) setLoading(false);
      }
    };

    loadLayout();
    const intervalId = setInterval(() => {
      loadLayout();
    }, 8000);
    return () => {
      active = false;
      clearInterval(intervalId);
    };
  }, [vendorId, selectedShowId, selectedHall]);

  const handleSaveLayout = async () => {
    if (!vendorId) return;
    setSavingLayout(true);
    setMessage("");
    try {
      const categoryTotal = CATEGORY_KEYS.reduce((sum, key) => {
        const value = Number(categoryRows[key]) || 0;
        return sum + value;
      }, 0);
      const rowsValue = Number(rows) || 10;
      if (categoryTotal > 0 && rowsValue !== categoryTotal) {
        setMessage(
          `Total rows (${rowsValue}) must equal the sum of category rows (${categoryTotal}). Update the category rows to match.`
        );
        return;
      }

      const payload = {
        vendor_id: vendorId,
        show_id: selectedShowId || undefined,
        hall: selectedHall || "Hall A",
        rows: rowsValue,
        columns: Number(columns) || 15,
        category_rows: {
          normal: Number(categoryRows.normal) || 0,
          executive: Number(categoryRows.executive) || 0,
          premium: Number(categoryRows.premium) || 0,
          vip: Number(categoryRows.vip) || 0,
        },
      };
      const data = await saveVendorSeatLayout(payload);
      layoutDirtyRef.current = false;
      setLayoutDirty(false);
      applyLayoutData(data, { forceConfig: true });
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

    const targetStatus =
      statusMode === "Unavailable" ? "Unavailable" : "Available";
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
      applyLayoutData(data);
      setMessage(data?.message || "Seat updated.");
    } catch (error) {
      setMessage(error.message || "Failed to update seat.");
    } finally {
      setUpdatingSeat("");
    }
  };

  const seatMap = useMemo(() => buildSeatMap(layout), [layout]);

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
                setLayoutDirty(false);
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
              onChange={(event) => {
                setLayoutDirty(true);
                setSelectedHall(event.target.value);
              }}
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
              onChange={(event) => {
                setLayoutDirty(true);
                setRows(event.target.value);
              }}
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
              onChange={(event) => {
                setLayoutDirty(true);
                setColumns(event.target.value);
              }}
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
                onChange={(event) => {
                  setLayoutDirty(true);
                  setCategoryRows((prev) => ({
                    ...prev,
                    [key]: event.target.value,
                  }));
                }}
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
            <p>Booked seats are locked. Use Unavailable for maintenance/repairs.</p>
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
        <div className="seat-layout seat-layout--fullwidth">
          <div>
            <div className="seat-mapHeader">
              <div className="seat-mapLabel">Seat Layout</div>
              <div className="seat-screen">
                <span>SCREEN</span>
                <div className="seat-curve" />
              </div>
            </div>

            <div className="seat-mapCard">
              <div className="seat-map" style={seatMapStyle}>
                {loading ? (
                  <div className="text-muted">Loading layout...</div>
                ) : (
                  dynamicSeatGroups.map((group) => (
                    <div className={`seat-group seat-group--${group.key}`} key={group.label}>
                      <div className="seat-groupTitle">{group.label}</div>
                      <div className="seat-groupRows">
                        {(group.rows || []).map((row) => (
                          <div className="seat-row" key={row}>
                            <div className="seat-rowLabel">{row}</div>
                            <div className="seat-rowSeats">
                              {dynamicSeatCols.map((col) => {
                                const key = `${row}${col}`;
                                const seat = seatMap.get(normalizeSeatLabel(key)) || null;
                                const status = getVendorSeatStatus(
                                  key,
                                  seat,
                                  soldSeatSet,
                                  unavailableSeatSet,
                                  reservedSeatSet
                                );
                                const isBlocked =
                                  status === "seat--sold" || status === "seat--reserved";
                                return (
                                  <Fragment key={key}>
                                    <button
                                      type="button"
                                      className={`seat seat--cat-${group.key} ${status}`}
                                      aria-label={`Seat ${key}`}
                                      disabled={isBlocked || updatingSeat === key}
                                      onClick={() =>
                                        handleSeatToggle(seat || { label: key, seat_type: group.key })
                                      }
                                    >
                                      {key}
                                    </button>
                                  </Fragment>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                )}

                <div className="seat-colLabels">
                  <div className="seat-colSpacer" />
                  {dynamicSeatCols.map((col) => (
                    <Fragment key={`col-${col}`}>
                      <div className="seat-colLabel">{col}</div>
                    </Fragment>
                  ))}
                </div>
              </div>

              <div className="seat-categoryLegend">
                <span className="seat-categoryLegendTitle">Seat Categories</span>
                {dynamicSeatGroups.map((group) => (
                  <span className="seat-legendItem" key={`cat-${group.key}`}>
                    <span className={`seat-legendBox category ${group.key}`} /> {group.label}
                  </span>
                ))}
              </div>

              <div className="seat-legend">
                <span className="seat-legendItem">
                  <span className="seat-legendBox available" /> Available
                </span>
                <span className="seat-legendItem">
                  <span className="seat-legendBox reserved" /> Reserved
                </span>
                <span className="seat-legendItem">
                  <span className="seat-legendBox sold" /> Booked
                </span>
                <span className="seat-legendItem">
                  <span className="seat-legendBox unavailable" /> Unavailable
                </span>
              </div>
            </div>
          </div>
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

function buildSeatMap(layout) {
  const seats = Array.isArray(layout?.seats) ? layout.seats : [];
  const seatMap = new Map();
  seats.forEach((seat) => {
    const row = String(seat.row_label || "").trim().toUpperCase();
    const column = String(seat.seat_number || "").trim();
    if (!row || !column) return;
    seatMap.set(normalizeSeatLabel(`${row}${column}`), seat);
  });
  return seatMap;
}

function capitalize(value) {
  const text = String(value || "");
  if (!text) return text;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function normalizeSeatLabel(value) {
  return String(value || "")
    .replace(/\s+/g, "")
    .toUpperCase()
    .trim();
}

function getVendorSeatStatus(key, seat, soldSeatSet, unavailableSeatSet, reservedSeatSet) {
  const normalized = normalizeSeatLabel(key);
  const seatStatus = String(seat?.status || "").toLowerCase();
  if (soldSeatSet.has(normalized) || seatStatus === "booked") return "seat--sold";
  if (unavailableSeatSet.has(normalized) || seatStatus === "unavailable") {
    return "seat--unavailable";
  }
  if (reservedSeatSet?.has?.(normalized) || seatStatus === "reserved") {
    return "seat--reserved";
  }
  return "seat--available";
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

