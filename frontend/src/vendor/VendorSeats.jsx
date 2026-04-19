import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import "../css/seatSelection.css";
import {
  createVendorHall,
  fetchVendorSeatLayout,
  fetchVendorHalls,
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

  const [hallRecords, setHallRecords] = useState([]);
  const [hallsLoading, setHallsLoading] = useState(false);
  const [hallActionLoading, setHallActionLoading] = useState(false);
  const hallOptions = useMemo(() => {
    const names = new Set(
      (Array.isArray(hallRecords) ? hallRecords : [])
        .map((item) => String(item?.hall || "").trim())
        .filter(Boolean)
    );
    return Array.from(names).sort((left, right) =>
      left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" })
    );
  }, [hallRecords]);

  const [selectedShowId, setSelectedShowId] = useState("");
  const [selectedHall, setSelectedHall] = useState("");
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

  useEffect(() => {
    if (!vendorId) return;
    let active = true;
    const loadHalls = async () => {
      setHallsLoading(true);
      try {
        const payload = await fetchVendorHalls({ vendor_id: vendorId });
        if (!active) return;
        setHallRecords(Array.isArray(payload?.halls) ? payload.halls : []);
      } catch (error) {
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
    if (!hallOptions.length) {
      setSelectedHall("");
      return;
    }
    const current = String(selectedHall || "").trim().toLowerCase();
    if (current && hallOptions.some((hall) => hall.toLowerCase() === current)) {
      return;
    }
    setSelectedHall(hallOptions[0]);
  }, [hallOptions, selectedHall]);

  const handleAddHall = async () => {
    if (!vendorId || hallActionLoading) return;
    setMessage("");
    setHallActionLoading(true);
    try {
      const result = await createVendorHall({ vendor_id: vendorId });
      const createdHall = String(result?.hall?.hall || "").trim();
      const payload = await fetchVendorHalls({ vendor_id: vendorId });
      setHallRecords(Array.isArray(payload?.halls) ? payload.halls : []);
      if (createdHall) {
        setSelectedHall(createdHall);
        setMessage(`${createdHall} created.`);
      }
    } catch (error) {
      setMessage(error.message || "Unable to add hall.");
    } finally {
      setHallActionLoading(false);
    }
  };

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
    const firstShow = vendorShows[0];
    setSelectedShowId(String(firstShow.id));
    if (firstShow?.hall) {
      setSelectedHall(String(firstShow.hall));
    }
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
    if (!selectedHall) {
      setMessage("Please add/select a hall first.");
      return;
    }
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
        hall: selectedHall,
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
    if (!selectedHall) {
      setMessage("Select a hall to update seat availability.");
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

  const seatInsights = useMemo(() => {
    const rowStats = [];
    const categoryBuckets = new Map(
      CATEGORY_KEYS.map((key) => [
        key,
        { key, total: 0, booked: 0, reserved: 0, unavailable: 0, available: 0 },
      ])
    );

    dynamicSeatGroups.forEach((group) => {
      const categoryKey = CATEGORY_KEYS.includes(group?.key) ? group.key : "normal";
      const rowsList = Array.isArray(group?.rows) ? group.rows : [];
      rowsList.forEach((rawRow) => {
        const row = normalizeSeatLabel(rawRow);
        if (!row) return;

        const rowBucket = {
          row,
          category: categoryKey,
          total: 0,
          booked: 0,
          reserved: 0,
          unavailable: 0,
          available: 0,
        };

        dynamicSeatCols.forEach((col) => {
          const seatLabel = `${row}${col}`;
          const seat = seatMap.get(normalizeSeatLabel(seatLabel)) || null;
          const status = getVendorSeatStatus(
            seatLabel,
            seat,
            soldSeatSet,
            unavailableSeatSet,
            reservedSeatSet
          );

          rowBucket.total += 1;
          if (status === "seat--sold") rowBucket.booked += 1;
          else if (status === "seat--reserved") rowBucket.reserved += 1;
          else if (status === "seat--unavailable") rowBucket.unavailable += 1;
          else rowBucket.available += 1;
        });

        rowBucket.pressure = rowBucket.total
          ? ((rowBucket.booked + rowBucket.reserved) / rowBucket.total) * 100
          : 0;
        rowStats.push(rowBucket);

        const categoryBucket = categoryBuckets.get(categoryKey);
        if (categoryBucket) {
          categoryBucket.total += rowBucket.total;
          categoryBucket.booked += rowBucket.booked;
          categoryBucket.reserved += rowBucket.reserved;
          categoryBucket.unavailable += rowBucket.unavailable;
          categoryBucket.available += rowBucket.available;
        }
      });
    });

    const totals = rowStats.reduce(
      (acc, row) => ({
        total: acc.total + row.total,
        booked: acc.booked + row.booked,
        reserved: acc.reserved + row.reserved,
        unavailable: acc.unavailable + row.unavailable,
        available: acc.available + row.available,
      }),
      { total: 0, booked: 0, reserved: 0, unavailable: 0, available: 0 }
    );

    const categoryStats = CATEGORY_KEYS.map((key) => {
      const bucket = categoryBuckets.get(key) || {
        key,
        total: 0,
        booked: 0,
        reserved: 0,
        unavailable: 0,
        available: 0,
      };
      const pressure = bucket.total ? ((bucket.booked + bucket.reserved) / bucket.total) * 100 : 0;
      return {
        ...bucket,
        pressure,
      };
    });

    const hotRows = [...rowStats]
      .sort((left, right) => {
        if (right.pressure !== left.pressure) return right.pressure - left.pressure;
        return right.booked - left.booked;
      })
      .slice(0, 5);

    const occupancy = totals.total ? ((totals.booked + totals.reserved) / totals.total) * 100 : 0;

    return {
      totals,
      occupancy,
      rowStats,
      categoryStats,
      hotRows,
    };
  }, [dynamicSeatCols, dynamicSeatGroups, seatMap, soldSeatSet, unavailableSeatSet, reservedSeatSet]);

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
              value={selectedHall}
              onChange={(event) => {
                setLayoutDirty(true);
                setSelectedHall(event.target.value);
              }}
            >
              <option value="">Select Hall</option>
              {hallOptions.map((hall) => (
                <option key={hall} value={hall}>
                  {hall}
                </option>
              ))}
            </select>
            <small className="text-muted d-block mt-1">
              {hallsLoading ? "Loading halls..." : "Hall names are auto-generated (Hall A, Hall B, Hall C...)."}
            </small>
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

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Seat Heatmap & Insights</h3>
            <p>Quickly spot crowded rows, weak zones, and category-level pressure.</p>
          </div>
        </div>

        <div className="vendor-seatInsightMetrics">
          <article className="vendor-seatInsightMetric">
            <span>Total Seats</span>
            <strong>{seatInsights.totals.total.toLocaleString()}</strong>
          </article>
          <article className="vendor-seatInsightMetric">
            <span>Occupied (Booked + Reserved)</span>
            <strong>{(seatInsights.totals.booked + seatInsights.totals.reserved).toLocaleString()}</strong>
          </article>
          <article className="vendor-seatInsightMetric">
            <span>Live Occupancy</span>
            <strong>{seatInsights.occupancy.toFixed(1)}%</strong>
          </article>
          <article className="vendor-seatInsightMetric">
            <span>Unavailable</span>
            <strong>{seatInsights.totals.unavailable.toLocaleString()}</strong>
          </article>
        </div>

        <div className="vendor-seatInsightLayout">
          <div className="vendor-seatHeatPanel">
            <div className="vendor-seatHeatHeader">
              <h4>Row Pressure Heatmap</h4>
              <p>Pressure = booked + reserved seats in each row.</p>
            </div>
            <div className="vendor-seatHeatRows">
              {seatInsights.rowStats.map((row) => {
                const tone = row.pressure >= 70 ? "hot" : row.pressure >= 40 ? "warm" : "cool";
                return (
                  <article key={`heat-${row.row}`} className={`vendor-seatHeatRow ${tone}`}>
                    <div className="vendor-seatHeatMeta">
                      <strong>Row {row.row}</strong>
                      <span>{capitalize(row.category)}</span>
                    </div>
                    <div className="vendor-seatHeatTrack">
                      <div
                        className="vendor-seatHeatFill"
                        style={{ width: `${Math.min(100, Math.max(0, row.pressure))}%` }}
                      />
                    </div>
                    <div className="vendor-seatHeatValue">
                      {row.pressure.toFixed(0)}% ({row.booked + row.reserved}/{row.total})
                    </div>
                  </article>
                );
              })}
              {seatInsights.rowStats.length === 0 ? (
                <div className="text-muted">No rows available for heatmap yet.</div>
              ) : null}
            </div>
          </div>

          <aside className="vendor-seatInsightSide">
            <section className="vendor-seatInsightBlock">
              <h4>Category Utilization</h4>
              <div className="vendor-seatCategoryList">
                {seatInsights.categoryStats.map((item) => (
                  <div className="vendor-seatCategoryItem" key={`category-${item.key}`}>
                    <div className="vendor-seatCategoryHead">
                      <span>{capitalize(item.key)}</span>
                      <strong>{item.pressure.toFixed(0)}%</strong>
                    </div>
                    <div className="vendor-seatCategoryTrack">
                      <div
                        className={`vendor-seatCategoryFill ${item.key}`}
                        style={{ width: `${Math.min(100, Math.max(0, item.pressure))}%` }}
                      />
                    </div>
                    <small>
                      {item.booked + item.reserved}/{item.total} occupied
                    </small>
                  </div>
                ))}
              </div>
            </section>

            <section className="vendor-seatInsightBlock">
              <h4>Hot Rows Watchlist</h4>
              <ul className="vendor-seatHotList">
                {seatInsights.hotRows.map((row) => (
                  <li key={`hot-${row.row}`}>
                    <span>Row {row.row}</span>
                    <strong>{row.pressure.toFixed(0)}%</strong>
                  </li>
                ))}
                {seatInsights.hotRows.length === 0 ? (
                  <li>
                    <span className="text-muted">No row activity yet.</span>
                  </li>
                ) : null}
              </ul>
            </section>
          </aside>
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

