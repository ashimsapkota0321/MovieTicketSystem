import { useEffect, useMemo, useState } from "react";
import { Pencil, Plus, Save, Trash2, X } from "lucide-react";
import {
  createVendorPricingRule,
  deleteVendorPricingRule,
  fetchVendorPricingRules,
  fetchVendorSeatLayout,
  saveVendorSeatLayout,
  updateVendorPricingRule,
} from "../lib/catalogApi";
import { useAppContext } from "../context/Appcontext";

const seatCategoryOptions = [
  { value: "ALL", label: "All Categories" },
  { value: "NORMAL", label: "Normal" },
  { value: "EXECUTIVE", label: "Executive" },
  { value: "PREMIUM", label: "Premium" },
  { value: "VIP", label: "VIP" },
];

const dayTypeOptions = [
  { value: "ALL", label: "All Days" },
  { value: "WEEKDAY", label: "Weekday" },
  { value: "WEEKEND", label: "Weekend" },
];

const adjustmentTypeOptions = [
  { value: "INCREMENT", label: "Add Amount" },
  { value: "FIXED", label: "Set Fixed Price" },
  { value: "PERCENT", label: "Percent Change" },
  { value: "MULTIPLIER", label: "Multiplier" },
];

function defaultFormValue() {
  return {
    name: "",
    movie_id: "",
    hall: "",
    seat_category: "ALL",
    day_type: "ALL",
    is_festival_pricing: false,
    festival_name: "",
    start_date: "",
    end_date: "",
    adjustment_type: "INCREMENT",
    adjustment_value: "",
    priority: 100,
    is_active: true,
  };
}

export default function VendorPricingRules() {
  const ctx = safeUseAppContext();
  const movies = useMemo(() => (Array.isArray(ctx?.movies) ? ctx.movies : []), [ctx?.movies]);
  const shows = useMemo(() => (Array.isArray(ctx?.showtimes) ? ctx.showtimes : []), [ctx?.showtimes]);

  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingRuleId, setEditingRuleId] = useState(null);
  const [form, setForm] = useState(defaultFormValue);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [priceHall, setPriceHall] = useState("Hall A");
  const [basePrices, setBasePrices] = useState({
    normal: "",
    executive: "",
    premium: "",
    vip: "",
  });
  const [layoutConfig, setLayoutConfig] = useState({
    rows: 10,
    columns: 15,
    categoryRows: { normal: 3, executive: 3, premium: 2, vip: 2 },
  });
  const [loadingBasePrices, setLoadingBasePrices] = useState(false);
  const [savingBasePrices, setSavingBasePrices] = useState(false);
  const [basePriceMessage, setBasePriceMessage] = useState("");
  const [basePriceError, setBasePriceError] = useState("");

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const data = await fetchVendorPricingRules();
        if (!active) return;
        setRules(Array.isArray(data) ? data : []);
      } catch (err) {
        if (!active) return;
        setError(err.message || "Failed to load pricing rules.");
      } finally {
        if (active) setLoading(false);
      }
    };
    load();
    return () => {
      active = false;
    };
  }, []);

  const movieMap = useMemo(() => {
    const next = new Map();
    for (const movie of movies) {
      const id = movie?.id;
      if (!id) continue;
      next.set(String(id), movie?.title || `Movie #${id}`);
    }
    return next;
  }, [movies]);

  const hallOptions = useMemo(() => {
    const set = new Set();
    for (const show of shows) {
      const hall = String(show?.hall || "").trim();
      if (hall) set.add(hall);
    }
    if (set.size === 0) set.add("Hall A");
    return Array.from(set);
  }, [shows]);

  useEffect(() => {
    if (!hallOptions.length) return;
    if (!hallOptions.includes(priceHall)) {
      setPriceHall(hallOptions[0]);
    }
  }, [hallOptions, priceHall]);

  useEffect(() => {
    if (!priceHall) return;
    let active = true;
    const loadBasePrices = async () => {
      setLoadingBasePrices(true);
      setBasePriceError("");
      try {
        const data = await fetchVendorSeatLayout({ hall: priceHall });
        if (!active) return;
        const categoryPrices = data?.category_prices || {};
        setBasePrices({
          normal: toInputPrice(categoryPrices.normal),
          executive: toInputPrice(categoryPrices.executive),
          premium: toInputPrice(categoryPrices.premium),
          vip: toInputPrice(categoryPrices.vip),
        });
        const inferredRows = inferCategoryRows(data?.seat_groups || []);
        setLayoutConfig({
          rows: Number(data?.total_rows) > 0 ? Number(data.total_rows) : 10,
          columns: Number(data?.total_columns) > 0 ? Number(data.total_columns) : 15,
          categoryRows: inferredRows,
        });
      } catch (err) {
        if (!active) return;
        setBasePriceError(err.message || "Failed to load category prices.");
      } finally {
        if (active) setLoadingBasePrices(false);
      }
    };
    loadBasePrices();
    return () => {
      active = false;
    };
  }, [priceHall]);

  const handleSaveBasePrices = async () => {
    if (!priceHall) return;
    setSavingBasePrices(true);
    setBasePriceError("");
    setBasePriceMessage("");
    try {
      await saveVendorSeatLayout({
        hall: priceHall,
        rows: Number(layoutConfig.rows) || 10,
        columns: Number(layoutConfig.columns) || 15,
        category_rows: {
          normal: Number(layoutConfig.categoryRows?.normal) || 0,
          executive: Number(layoutConfig.categoryRows?.executive) || 0,
          premium: Number(layoutConfig.categoryRows?.premium) || 0,
          vip: Number(layoutConfig.categoryRows?.vip) || 0,
        },
        category_prices: {
          normal: toNumberPrice(basePrices.normal),
          executive: toNumberPrice(basePrices.executive),
          premium: toNumberPrice(basePrices.premium),
          vip: toNumberPrice(basePrices.vip),
        },
      });
      setBasePriceMessage("Seat category prices saved.");
    } catch (err) {
      setBasePriceError(err.message || "Failed to save category prices.");
    } finally {
      setSavingBasePrices(false);
    }
  };

  const resetForm = () => {
    setEditingRuleId(null);
    setForm(defaultFormValue());
  };

  const handleEdit = (rule) => {
    setEditingRuleId(rule.id);
    setForm({
      name: String(rule.name || ""),
      movie_id: rule.movie_id ? String(rule.movie_id) : "",
      hall: String(rule.hall || ""),
      seat_category: String(rule.seat_category || "ALL").toUpperCase(),
      day_type: String(rule.day_type || "ALL").toUpperCase(),
      is_festival_pricing: Boolean(rule.is_festival_pricing),
      festival_name: String(rule.festival_name || ""),
      start_date: String(rule.start_date || ""),
      end_date: String(rule.end_date || ""),
      adjustment_type: String(rule.adjustment_type || "INCREMENT").toUpperCase(),
      adjustment_value: rule.adjustment_value == null ? "" : String(rule.adjustment_value),
      priority: Number(rule.priority || 100),
      is_active: Boolean(rule.is_active),
    });
    setError("");
    setNotice("");
  };

  const buildPayload = () => {
    const adjustmentValue = Number(form.adjustment_value);
    const payload = {
      name: String(form.name || "").trim(),
      movie_id: form.movie_id ? Number(form.movie_id) : null,
      hall: String(form.hall || "").trim() || null,
      seat_category: form.seat_category,
      day_type: form.day_type,
      is_festival_pricing: Boolean(form.is_festival_pricing),
      festival_name: String(form.festival_name || "").trim() || null,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      adjustment_type: form.adjustment_type,
      adjustment_value: Number.isFinite(adjustmentValue) ? adjustmentValue : null,
      priority: Number.isFinite(Number(form.priority)) ? Number(form.priority) : 100,
      is_active: Boolean(form.is_active),
    };
    if (!payload.is_festival_pricing) {
      payload.festival_name = null;
      payload.start_date = null;
      payload.end_date = null;
    }
    return payload;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setNotice("");

    const payload = buildPayload();
    if (!payload.name) {
      setError("Rule name is required.");
      return;
    }
    if (payload.adjustment_value === null || payload.adjustment_value < 0) {
      setError("Adjustment value must be a valid non-negative number.");
      return;
    }

    setSaving(true);
    try {
      if (editingRuleId) {
        const updated = await updateVendorPricingRule(editingRuleId, payload);
        setRules((prev) => prev.map((item) => (item.id === editingRuleId ? { ...item, ...updated } : item)));
        setNotice("Pricing rule updated.");
      } else {
        const created = await createVendorPricingRule(payload);
        setRules((prev) => [...prev, created].sort((a, b) => Number(a.priority || 0) - Number(b.priority || 0)));
        setNotice("Pricing rule created.");
      }
      resetForm();
    } catch (err) {
      setError(err.message || "Failed to save pricing rule.");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (rule) => {
    const confirmDelete = window.confirm(`Delete pricing rule \"${rule.name}\"?`);
    if (!confirmDelete) return;

    setError("");
    setNotice("");
    try {
      await deleteVendorPricingRule(rule.id);
      setRules((prev) => prev.filter((item) => item.id !== rule.id));
      if (editingRuleId === rule.id) resetForm();
      setNotice("Pricing rule deleted.");
    } catch (err) {
      setError(err.message || "Failed to delete pricing rule.");
    }
  };

  return (
    <div className="vendor-dashboard">
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3">
        <div>
          <h2 className="mb-1">Dynamic Pricing Rules</h2>
          <p className="text-muted mb-0">
            Configure weekday/weekend, seat-category, and festival price adjustments.
          </p>
        </div>
      </div>

      <div className="vendor-breadcrumb">
        <span>Pricing</span>
        <span className="vendor-dot">&#8226;</span>
        <span>Rules</span>
      </div>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Seat Category Base Prices</h3>
            <p>Manage hall-wise base ticket price for each seat category.</p>
          </div>
        </div>

        {basePriceError ? <div className="alert alert-danger mb-3">{basePriceError}</div> : null}
        {basePriceMessage ? <div className="alert alert-success mb-3">{basePriceMessage}</div> : null}

        <div className="vendor-pricing-grid">
          <label className="form-label">
            Hall
            <select
              className="form-select"
              value={priceHall}
              onChange={(event) => setPriceHall(event.target.value)}
            >
              {hallOptions.map((hall) => (
                <option key={hall} value={hall}>
                  {hall}
                </option>
              ))}
            </select>
          </label>

          <label className="form-label">
            Normal Price (NPR)
            <input
              className="form-control"
              type="number"
              min="0"
              step="0.01"
              value={basePrices.normal}
              onChange={(event) =>
                setBasePrices((prev) => ({ ...prev, normal: event.target.value }))
              }
              disabled={loadingBasePrices}
            />
          </label>

          <label className="form-label">
            Executive Price (NPR)
            <input
              className="form-control"
              type="number"
              min="0"
              step="0.01"
              value={basePrices.executive}
              onChange={(event) =>
                setBasePrices((prev) => ({ ...prev, executive: event.target.value }))
              }
              disabled={loadingBasePrices}
            />
          </label>

          <label className="form-label">
            Premium Price (NPR)
            <input
              className="form-control"
              type="number"
              min="0"
              step="0.01"
              value={basePrices.premium}
              onChange={(event) =>
                setBasePrices((prev) => ({ ...prev, premium: event.target.value }))
              }
              disabled={loadingBasePrices}
            />
          </label>

          <label className="form-label">
            VIP Price (NPR)
            <input
              className="form-control"
              type="number"
              min="0"
              step="0.01"
              value={basePrices.vip}
              onChange={(event) =>
                setBasePrices((prev) => ({ ...prev, vip: event.target.value }))
              }
              disabled={loadingBasePrices}
            />
          </label>
        </div>

        <div className="vendor-pricing-actions mt-3">
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleSaveBasePrices}
            disabled={savingBasePrices || loadingBasePrices}
          >
            <Save size={16} />
            {savingBasePrices ? "Saving..." : "Save Category Prices"}
          </button>
        </div>
      </section>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>{editingRuleId ? "Edit Pricing Rule" : "Create Pricing Rule"}</h3>
            <p>Rule priority is applied from lowest number to highest number.</p>
          </div>
          {editingRuleId ? (
            <button type="button" className="vendor-chip muted" onClick={resetForm}>
              <X size={14} />
              Cancel Edit
            </button>
          ) : null}
        </div>

        {error ? <div className="alert alert-danger mb-3">{error}</div> : null}
        {notice ? <div className="alert alert-success mb-3">{notice}</div> : null}

        <form onSubmit={handleSubmit} className="vendor-pricing-form">
          <div className="vendor-pricing-grid">
            <label className="form-label">
              Rule Name
              <input
                className="form-control"
                value={form.name}
                onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
                placeholder="Weekend premium boost"
                required
              />
            </label>

            <label className="form-label">
              Movie Scope
              <select
                className="form-select"
                value={form.movie_id}
                onChange={(event) => setForm((prev) => ({ ...prev, movie_id: event.target.value }))}
              >
                <option value="">All Movies</option>
                {movies.map((movie) => (
                  <option key={movie.id} value={movie.id}>
                    {movie.title || `Movie #${movie.id}`}
                  </option>
                ))}
              </select>
            </label>

            <label className="form-label">
              Hall Scope
              <input
                className="form-control"
                value={form.hall}
                onChange={(event) => setForm((prev) => ({ ...prev, hall: event.target.value }))}
                placeholder="Hall A (leave blank for all halls)"
              />
            </label>

            <label className="form-label">
              Seat Category
              <select
                className="form-select"
                value={form.seat_category}
                onChange={(event) => setForm((prev) => ({ ...prev, seat_category: event.target.value }))}
              >
                {seatCategoryOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="form-label">
              Day Type
              <select
                className="form-select"
                value={form.day_type}
                onChange={(event) => setForm((prev) => ({ ...prev, day_type: event.target.value }))}
              >
                {dayTypeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="form-label">
              Adjustment Type
              <select
                className="form-select"
                value={form.adjustment_type}
                onChange={(event) => setForm((prev) => ({ ...prev, adjustment_type: event.target.value }))}
              >
                {adjustmentTypeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="form-label">
              Adjustment Value
              <input
                className="form-control"
                type="number"
                min="0"
                step="0.01"
                value={form.adjustment_value}
                onChange={(event) => setForm((prev) => ({ ...prev, adjustment_value: event.target.value }))}
                placeholder="e.g. 50"
                required
              />
            </label>

            <label className="form-label">
              Priority
              <input
                className="form-control"
                type="number"
                min="1"
                max="9999"
                value={form.priority}
                onChange={(event) => setForm((prev) => ({ ...prev, priority: event.target.value }))}
              />
            </label>
          </div>

          <div className="vendor-pricing-flags">
            <label className="form-check">
              <input
                className="form-check-input"
                type="checkbox"
                checked={form.is_festival_pricing}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, is_festival_pricing: event.target.checked }))
                }
              />
              <span className="form-check-label">Festival Pricing Rule</span>
            </label>

            <label className="form-check">
              <input
                className="form-check-input"
                type="checkbox"
                checked={form.is_active}
                onChange={(event) => setForm((prev) => ({ ...prev, is_active: event.target.checked }))}
              />
              <span className="form-check-label">Active</span>
            </label>
          </div>

          {form.is_festival_pricing ? (
            <div className="vendor-pricing-grid vendor-pricing-grid--festival">
              <label className="form-label">
                Festival Name
                <input
                  className="form-control"
                  value={form.festival_name}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, festival_name: event.target.value }))
                  }
                  placeholder="Dashain"
                />
              </label>

              <label className="form-label">
                Start Date
                <input
                  className="form-control"
                  type="date"
                  value={form.start_date}
                  onChange={(event) => setForm((prev) => ({ ...prev, start_date: event.target.value }))}
                />
              </label>

              <label className="form-label">
                End Date
                <input
                  className="form-control"
                  type="date"
                  value={form.end_date}
                  onChange={(event) => setForm((prev) => ({ ...prev, end_date: event.target.value }))}
                />
              </label>
            </div>
          ) : null}

          <div className="vendor-pricing-actions">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {editingRuleId ? <Save size={16} /> : <Plus size={16} />}
              {saving ? "Saving..." : editingRuleId ? "Update Rule" : "Create Rule"}
            </button>
          </div>
        </form>
      </section>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Configured Rules</h3>
            <p>{loading ? "Loading rules..." : `${rules.length} rule(s) available.`}</p>
          </div>
        </div>

        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Scope</th>
                <th>Trigger</th>
                <th>Adjustment</th>
                <th>Priority</th>
                <th>Status</th>
                <th className="text-end">Actions</th>
              </tr>
            </thead>
            <tbody>
              {!loading && rules.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-muted py-3">
                    No pricing rules configured yet.
                  </td>
                </tr>
              ) : null}

              {rules.map((rule) => {
                const movieTitle = rule.movie_id ? movieMap.get(String(rule.movie_id)) || `Movie #${rule.movie_id}` : "All Movies";
                const trigger = [
                  rule.day_type || "ALL",
                  rule.seat_category || "ALL",
                  rule.is_festival_pricing ? rule.festival_name || "Festival" : null,
                ]
                  .filter(Boolean)
                  .join(" / ");

                return (
                  <tr key={rule.id}>
                    <td>{rule.name}</td>
                    <td>
                      <div>{movieTitle}</div>
                      <small className="text-muted">{rule.hall || "All Halls"}</small>
                    </td>
                    <td>{trigger}</td>
                    <td>
                      {rule.adjustment_type} : {Number(rule.adjustment_value || 0).toFixed(2)}
                    </td>
                    <td>{rule.priority}</td>
                    <td>
                      <span className={`vendor-rule-status ${rule.is_active ? "active" : "inactive"}`}>
                        {rule.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td>
                      <div className="vendor-actionRow justify-content-end">
                        <button
                          type="button"
                          className="vendor-actionIcon"
                          onClick={() => handleEdit(rule)}
                          aria-label="Edit rule"
                        >
                          <Pencil size={18} />
                        </button>
                        <button
                          type="button"
                          className="vendor-actionIcon"
                          onClick={() => handleDelete(rule)}
                          aria-label="Delete rule"
                        >
                          <Trash2 size={18} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function safeUseAppContext() {
  try {
    return useAppContext();
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

function toInputPrice(value) {
  if (value === null || value === undefined || value === "") return "";
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) return "";
  return String(numeric);
}

function toNumberPrice(value) {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) return null;
  return numeric;
}
