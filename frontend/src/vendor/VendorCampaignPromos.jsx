import { useEffect, useMemo, useState } from "react";
import {
  Clock3,
  Megaphone,
  PercentCircle,
  Play,
  Save,
  Sparkles,
  Trash2,
  Users,
} from "lucide-react";
import {
  createVendorCampaign,
  createVendorPromoCode,
  deleteVendorPromoCode,
  fetchVendorCampaigns,
  fetchVendorPromoCodes,
  runVendorCampaign,
  updateVendorCampaign,
  updateVendorPromoCode,
} from "../lib/catalogApi";
import { useAppContext } from "../context/Appcontext";
import { useVendorToast } from "./VendorToastContext";

const seatScopes = ["ALL", "NORMAL", "EXECUTIVE", "PREMIUM", "VIP"];
const discountTypes = ["PERCENTAGE", "FIXED", "BOGO"];
const campaignChannels = ["PUSH", "SMS", "BOTH"];
const weekdays = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"];

const promoPresets = [
  {
    key: "bogo-tuesday",
    label: "BOGO Tuesday",
    apply: () => ({
      discount_type: "BOGO",
      discount_value: "1",
      allowed_weekdays: ["TUE"],
      is_flash_sale: false,
      requires_student: false,
      seat_category_scope: "ALL",
    }),
  },
  {
    key: "student-executive",
    label: "Student Executive 20%",
    apply: () => ({
      discount_type: "PERCENTAGE",
      discount_value: "20",
      seat_category_scope: "EXECUTIVE",
      requires_student: true,
      is_flash_sale: false,
      allowed_weekdays: [],
    }),
  },
  {
    key: "flash-2h",
    label: "2-Hour Flash Sale",
    apply: () => {
      const now = new Date();
      const end = new Date(now.getTime() + 2 * 60 * 60 * 1000);
      return {
        discount_type: "PERCENTAGE",
        discount_value: "15",
        is_flash_sale: true,
        valid_from: toDateTimeLocalValue(now.toISOString()),
        valid_until: toDateTimeLocalValue(end.toISOString()),
      };
    },
  },
];

function emptyPromoForm() {
  return {
    code: "",
    title: "",
    description: "",
    discount_type: "PERCENTAGE",
    discount_value: "",
    min_booking_amount: "0",
    max_discount_amount: "",
    usage_limit: "",
    per_user_limit: "",
    seat_category_scope: "ALL",
    requires_student: false,
    allowed_weekdays: [],
    valid_from: "",
    valid_until: "",
    is_flash_sale: false,
    is_active: true,
  };
}

function emptyCampaignForm() {
  return {
    name: "",
    message_template:
      "Hi {first_name}, thanks for watching {last_movie}. Catch {next_movie} this week with {promo_code}!",
    delivery_channel: "BOTH",
    target_movie_id: "",
    recommended_movie_id: "",
    promo_code_id: "",
    min_days_since_booking: "0",
    scheduled_at: "",
    run_now: false,
  };
}

export default function VendorCampaignPromos() {
  const ctx = safeUseAppContext();
  const movies = useMemo(() => (Array.isArray(ctx?.movies) ? ctx.movies : []), [ctx?.movies]);

  const [promos, setPromos] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [savingPromo, setSavingPromo] = useState(false);
  const [savingCampaign, setSavingCampaign] = useState(false);
  const [runningCampaignId, setRunningCampaignId] = useState(null);
  const [editingPromoId, setEditingPromoId] = useState(null);
  const [promoForm, setPromoForm] = useState(emptyPromoForm);
  const [campaignForm, setCampaignForm] = useState(emptyCampaignForm);
  const { pushToast } = useVendorToast();

  const activePromos = useMemo(
    () => promos.filter((item) => item.is_active).length,
    [promos]
  );
  const scheduledCampaigns = useMemo(
    () => campaigns.filter((item) => item.status === "SCHEDULED").length,
    [campaigns]
  );
  const totalDispatches = useMemo(
    () =>
      campaigns.reduce(
        (total, item) => total + Number(item.sent_count || 0) + Number(item.failed_count || 0),
        0
      ),
    [campaigns]
  );

  const loadData = async () => {
    setLoading(true);
    try {
      const [promoData, campaignData] = await Promise.all([
        fetchVendorPromoCodes(),
        fetchVendorCampaigns(),
      ]);
      setPromos(Array.isArray(promoData) ? promoData : []);
      setCampaigns(Array.isArray(campaignData) ? campaignData : []);
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Data load failed",
        message: err.message || "Failed to load campaigns and promo codes.",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const resetPromoForm = () => {
    setEditingPromoId(null);
    setPromoForm(emptyPromoForm());
  };

  const resetCampaignForm = () => {
    setCampaignForm(emptyCampaignForm());
  };

  const handlePromoSubmit = async (event) => {
    event.preventDefault();

    if (!String(promoForm.code || "").trim() || !String(promoForm.title || "").trim()) {
      pushToast({
        tone: "warning",
        title: "Missing fields",
        message: "Promo code and title are required.",
      });
      return;
    }

    const payload = {
      ...promoForm,
      code: String(promoForm.code || "").trim().toUpperCase(),
      title: String(promoForm.title || "").trim(),
      description: String(promoForm.description || "").trim(),
      discount_value: Number(promoForm.discount_value || 0),
      min_booking_amount: Number(promoForm.min_booking_amount || 0),
      max_discount_amount:
        promoForm.max_discount_amount === "" ? null : Number(promoForm.max_discount_amount),
      usage_limit: promoForm.usage_limit === "" ? null : Number(promoForm.usage_limit),
      per_user_limit: promoForm.per_user_limit === "" ? null : Number(promoForm.per_user_limit),
      valid_from: promoForm.valid_from || null,
      valid_until: promoForm.valid_until || null,
    };

    setSavingPromo(true);
    try {
      if (editingPromoId) {
        await updateVendorPromoCode(editingPromoId, payload);
        pushToast({ tone: "success", title: "Promo updated", message: "Promo code updated." });
      } else {
        await createVendorPromoCode(payload);
        pushToast({ tone: "success", title: "Promo created", message: "Promo code created." });
      }
      resetPromoForm();
      await loadData();
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Promo save failed",
        message: err.message || "Failed to save promo code.",
      });
    } finally {
      setSavingPromo(false);
    }
  };

  const handleEditPromo = (promo) => {
    setEditingPromoId(promo.id);
    setPromoForm({
      code: String(promo.code || ""),
      title: String(promo.title || ""),
      description: String(promo.description || ""),
      discount_type: String(promo.discount_type || "PERCENTAGE").toUpperCase(),
      discount_value: String(promo.discount_value ?? ""),
      min_booking_amount: String(promo.min_booking_amount ?? "0"),
      max_discount_amount: promo.max_discount_amount == null ? "" : String(promo.max_discount_amount),
      usage_limit: promo.usage_limit == null ? "" : String(promo.usage_limit),
      per_user_limit: promo.per_user_limit == null ? "" : String(promo.per_user_limit),
      seat_category_scope: String(promo.seat_category_scope || "ALL").toUpperCase(),
      requires_student: Boolean(promo.requires_student),
      allowed_weekdays: Array.isArray(promo.allowed_weekdays) ? promo.allowed_weekdays : [],
      valid_from: toDateTimeLocalValue(promo.valid_from),
      valid_until: toDateTimeLocalValue(promo.valid_until),
      is_flash_sale: Boolean(promo.is_flash_sale),
      is_active: Boolean(promo.is_active),
    });
  };

  const handleDeletePromo = async (promo) => {
    if (!window.confirm(`Delete promo code ${promo.code}?`)) return;

    try {
      await deleteVendorPromoCode(promo.id);
      if (editingPromoId === promo.id) resetPromoForm();
      pushToast({ tone: "success", title: "Promo deleted", message: "Promo code deleted." });
      await loadData();
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Promo delete failed",
        message: err.message || "Failed to delete promo code.",
      });
    }
  };

  const handleCampaignSubmit = async (event) => {
    event.preventDefault();

    if (!String(campaignForm.name || "").trim()) {
      pushToast({
        tone: "warning",
        title: "Missing campaign name",
        message: "Campaign name is required.",
      });
      return;
    }

    const payload = {
      ...campaignForm,
      name: String(campaignForm.name || "").trim(),
      message_template: String(campaignForm.message_template || "").trim(),
      target_movie_id: campaignForm.target_movie_id ? Number(campaignForm.target_movie_id) : null,
      recommended_movie_id: campaignForm.recommended_movie_id
        ? Number(campaignForm.recommended_movie_id)
        : null,
      promo_code_id: campaignForm.promo_code_id ? Number(campaignForm.promo_code_id) : null,
      min_days_since_booking: Number(campaignForm.min_days_since_booking || 0),
      scheduled_at: campaignForm.scheduled_at || null,
      run_now: Boolean(campaignForm.run_now),
    };

    setSavingCampaign(true);
    try {
      await createVendorCampaign(payload);
      pushToast({
        tone: "success",
        title: campaignForm.run_now ? "Campaign dispatched" : "Campaign created",
        message: campaignForm.run_now ? "Campaign created and dispatched." : "Campaign created.",
      });
      resetCampaignForm();
      await loadData();
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Campaign create failed",
        message: err.message || "Failed to create campaign.",
      });
    } finally {
      setSavingCampaign(false);
    }
  };

  const handleRunCampaign = async (campaignId) => {
    setRunningCampaignId(campaignId);
    try {
      const result = await runVendorCampaign(campaignId);
      const sent = Number(result?.dispatch?.sent_count || 0);
      const failed = Number(result?.dispatch?.failed_count || 0);
      pushToast({
        tone: failed > 0 ? "warning" : "success",
        title: "Campaign run complete",
        message: `Campaign dispatched. Sent: ${sent}, Failed: ${failed}.`,
      });
      await loadData();
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Campaign run failed",
        message: err.message || "Failed to run campaign.",
      });
    } finally {
      setRunningCampaignId(null);
    }
  };

  const handleCampaignStatusChange = async (campaignId, statusValue) => {
    try {
      await updateVendorCampaign(campaignId, { status: statusValue });
      pushToast({ tone: "info", title: "Status updated", message: "Campaign status updated." });
      await loadData();
    } catch (err) {
      pushToast({
        tone: "error",
        title: "Status update failed",
        message: err.message || "Failed to update campaign status.",
      });
    }
  };

  const applyPromoPreset = (presetKey) => {
    const preset = promoPresets.find((item) => item.key === presetKey);
    if (!preset) return;
    const nextValues = preset.apply();
    setPromoForm((prev) => ({ ...prev, ...nextValues }));
  };

  return (
    <div className="vendor-dashboard">
      <div className="vendor-marketing-hero mb-3">
        <div>
          <p className="vendor-marketing-eyebrow mb-1">Growth Toolkit</p>
          <h2 className="mb-1">Campaigns & Promo Engine</h2>
          <p className="text-muted mb-0">
            Convert past attendees with targeted nudges, time-boxed offers, and seat-aware discounts.
          </p>
        </div>
        <div className="vendor-marketing-metrics">
          <div className="vendor-marketing-metric">
            <span>Active Promos</span>
            <strong>{activePromos}</strong>
          </div>
          <div className="vendor-marketing-metric">
            <span>Scheduled Campaigns</span>
            <strong>{scheduledCampaigns}</strong>
          </div>
          <div className="vendor-marketing-metric">
            <span>Total Dispatches</span>
            <strong>{totalDispatches}</strong>
          </div>
        </div>
      </div>

      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3 mb-3">
        <div>
          <p className="vendor-breadcrumb mb-0">
            <span>Marketing</span>
            <span className="vendor-dot">&#8226;</span>
            <span>Campaigns & Promos</span>
          </p>
        </div>
      </div>

      <section className="vendor-card mb-3">
        <div className="vendor-card-header">
          <div>
            <h3>
              <PercentCircle size={18} className="me-2" />
              Custom Promo Codes
            </h3>
            <p>Create BOGO Tuesday, seat-targeted, student-only, or flash promo rules.</p>
          </div>
          <div className="vendor-marketing-preset-row">
            {promoPresets.map((preset) => (
              <button
                key={preset.key}
                type="button"
                className="vendor-chip"
                onClick={() => applyPromoPreset(preset.key)}
              >
                <Sparkles size={14} />
                {preset.label}
              </button>
            ))}
          </div>
        </div>

        <form className="row g-2 mb-3" onSubmit={handlePromoSubmit}>
          <div className="col-md-2">
            <input
              className="form-control"
              placeholder="Code"
              value={promoForm.code}
              onChange={(event) => setPromoForm((prev) => ({ ...prev, code: event.target.value }))}
            />
          </div>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Title"
              value={promoForm.title}
              onChange={(event) => setPromoForm((prev) => ({ ...prev, title: event.target.value }))}
            />
          </div>
          <div className="col-md-2">
            <select
              className="form-select"
              value={promoForm.discount_type}
              onChange={(event) => setPromoForm((prev) => ({ ...prev, discount_type: event.target.value }))}
            >
              {discountTypes.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              placeholder="Discount"
              type="number"
              min="0"
              step="0.01"
              value={promoForm.discount_value}
              onChange={(event) => setPromoForm((prev) => ({ ...prev, discount_value: event.target.value }))}
            />
          </div>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Description"
              value={promoForm.description}
              onChange={(event) => setPromoForm((prev) => ({ ...prev, description: event.target.value }))}
            />
          </div>
          <div className="col-md-2">
            <select
              className="form-select"
              value={promoForm.seat_category_scope}
              onChange={(event) =>
                setPromoForm((prev) => ({ ...prev, seat_category_scope: event.target.value }))
              }
            >
              {seatScopes.map((scope) => (
                <option key={scope} value={scope}>
                  Seat: {scope}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              placeholder="Min amount"
              type="number"
              min="0"
              step="0.01"
              value={promoForm.min_booking_amount}
              onChange={(event) =>
                setPromoForm((prev) => ({ ...prev, min_booking_amount: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              placeholder="Max discount"
              type="number"
              min="0"
              step="0.01"
              value={promoForm.max_discount_amount}
              onChange={(event) =>
                setPromoForm((prev) => ({ ...prev, max_discount_amount: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              placeholder="Usage limit"
              type="number"
              min="1"
              value={promoForm.usage_limit}
              onChange={(event) => setPromoForm((prev) => ({ ...prev, usage_limit: event.target.value }))}
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              placeholder="Per-user limit"
              type="number"
              min="1"
              value={promoForm.per_user_limit}
              onChange={(event) =>
                setPromoForm((prev) => ({ ...prev, per_user_limit: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="datetime-local"
              value={promoForm.valid_from}
              onChange={(event) => setPromoForm((prev) => ({ ...prev, valid_from: event.target.value }))}
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="datetime-local"
              value={promoForm.valid_until}
              onChange={(event) => setPromoForm((prev) => ({ ...prev, valid_until: event.target.value }))}
            />
          </div>
          <div className="col-12 d-flex flex-wrap gap-2 align-items-center">
            {weekdays.map((day) => {
              const selected = promoForm.allowed_weekdays.includes(day);
              return (
                <label key={day} className="vendor-chip muted" style={{ cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    className="form-check-input me-1"
                    checked={selected}
                    onChange={(event) =>
                      setPromoForm((prev) => ({
                        ...prev,
                        allowed_weekdays: event.target.checked
                          ? [...prev.allowed_weekdays, day]
                          : prev.allowed_weekdays.filter((item) => item !== day),
                      }))
                    }
                  />
                  {day}
                </label>
              );
            })}
            <label className="form-check d-inline-flex align-items-center ms-2">
              <input
                type="checkbox"
                className="form-check-input"
                checked={promoForm.requires_student}
                onChange={(event) =>
                  setPromoForm((prev) => ({ ...prev, requires_student: event.target.checked }))
                }
              />
              <span className="ms-1">Student only</span>
            </label>
            <label className="form-check d-inline-flex align-items-center">
              <input
                type="checkbox"
                className="form-check-input"
                checked={promoForm.is_flash_sale}
                onChange={(event) =>
                  setPromoForm((prev) => ({ ...prev, is_flash_sale: event.target.checked }))
                }
              />
              <span className="ms-1">Flash sale</span>
            </label>
            <label className="form-check d-inline-flex align-items-center">
              <input
                type="checkbox"
                className="form-check-input"
                checked={promoForm.is_active}
                onChange={(event) => setPromoForm((prev) => ({ ...prev, is_active: event.target.checked }))}
              />
              <span className="ms-1">Active</span>
            </label>
          </div>
          <div className="col-12 d-flex gap-2">
            <button type="submit" className="btn btn-primary" disabled={savingPromo}>
              <Save size={16} className="me-1" />
              {savingPromo ? "Saving..." : editingPromoId ? "Update Promo" : "Create Promo"}
            </button>
            {editingPromoId ? (
              <button type="button" className="btn btn-outline-secondary" onClick={resetPromoForm}>
                Cancel Edit
              </button>
            ) : null}
          </div>
        </form>

        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Rule</th>
                <th>Limits</th>
                <th>Window</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {promos.map((promo) => (
                <tr key={promo.id}>
                  <td>
                    <div className="fw-semibold">{promo.code}</div>
                    <small className="text-muted">{promo.title}</small>
                  </td>
                  <td>
                    <div>
                      {promo.discount_type} ({promo.discount_value})
                    </div>
                    <small className="text-muted">
                      Seat: {promo.seat_category_scope} {promo.requires_student ? "• Student" : ""}
                    </small>
                  </td>
                  <td>
                    <div>
                      Used {promo.usage_count}
                      {promo.usage_limit ? ` / ${promo.usage_limit}` : ""}
                    </div>
                    <small className="text-muted">Per user: {promo.per_user_limit || "-"}</small>
                  </td>
                  <td>
                    <div>{formatShortDate(promo.valid_from)}</div>
                    <small className="text-muted">to {formatShortDate(promo.valid_until)}</small>
                  </td>
                  <td>
                    <span className={`vendor-rule-status ${promo.is_active ? "active" : "inactive"}`}>
                      {promo.is_active ? "ACTIVE" : "INACTIVE"}
                    </span>
                    {promo.is_flash_sale ? (
                      <span className="vendor-rule-status vendor-rule-status-flash ms-2">FLASH</span>
                    ) : null}
                  </td>
                  <td>
                    <div className="d-flex gap-2">
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-primary"
                        onClick={() => handleEditPromo(promo)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-danger"
                        onClick={() => handleDeletePromo(promo)}
                      >
                        <Trash2 size={14} className="me-1" />
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && promos.length === 0 ? (
                <tr>
                  <td colSpan="6">No promo codes yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>
              <Megaphone size={18} className="me-2" />
              Targeted Campaigns
            </h3>
            <p>Push or SMS alerts for past attendees, with optional promo linking.</p>
          </div>
          <div className="vendor-chip muted">
            <Users size={14} />
            Past attendees audience
          </div>
        </div>

        <form className="row g-2 mb-3" onSubmit={handleCampaignSubmit}>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Campaign name"
              value={campaignForm.name}
              onChange={(event) => setCampaignForm((prev) => ({ ...prev, name: event.target.value }))}
            />
          </div>
          <div className="col-md-2">
            <select
              className="form-select"
              value={campaignForm.delivery_channel}
              onChange={(event) =>
                setCampaignForm((prev) => ({ ...prev, delivery_channel: event.target.value }))
              }
            >
              {campaignChannels.map((channel) => (
                <option key={channel} value={channel}>
                  {channel}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-2">
            <select
              className="form-select"
              value={campaignForm.target_movie_id}
              onChange={(event) =>
                setCampaignForm((prev) => ({ ...prev, target_movie_id: event.target.value }))
              }
            >
              <option value="">All watched movies</option>
              {movies.map((movie) => (
                <option key={movie.id} value={movie.id}>
                  Watched: {movie.title}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-2">
            <select
              className="form-select"
              value={campaignForm.recommended_movie_id}
              onChange={(event) =>
                setCampaignForm((prev) => ({ ...prev, recommended_movie_id: event.target.value }))
              }
            >
              <option value="">No recommendation</option>
              {movies.map((movie) => (
                <option key={movie.id} value={movie.id}>
                  Recommend: {movie.title}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-3">
            <select
              className="form-select"
              value={campaignForm.promo_code_id}
              onChange={(event) =>
                setCampaignForm((prev) => ({ ...prev, promo_code_id: event.target.value }))
              }
            >
              <option value="">No promo code</option>
              {promos
                .filter((promo) => promo.is_active)
                .map((promo) => (
                  <option key={promo.id} value={promo.id}>
                    {promo.code} - {promo.title}
                  </option>
                ))}
            </select>
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="0"
              placeholder="Min days (0 = all)"
              value={campaignForm.min_days_since_booking}
              onChange={(event) =>
                setCampaignForm((prev) => ({ ...prev, min_days_since_booking: event.target.value }))
              }
            />
          </div>
          <div className="col-md-3">
            <input
              className="form-control"
              type="datetime-local"
              value={campaignForm.scheduled_at}
              onChange={(event) =>
                setCampaignForm((prev) => ({ ...prev, scheduled_at: event.target.value }))
              }
            />
          </div>
          <div className="col-md-7">
            <textarea
              className="form-control"
              rows="3"
              placeholder="Message template"
              value={campaignForm.message_template}
              onChange={(event) =>
                setCampaignForm((prev) => ({ ...prev, message_template: event.target.value }))
              }
            />
            <small className="text-muted">
              Supported variables: {"{first_name}"}, {"{full_name}"}, {"{last_movie}"}, {"{next_movie}"}, {"{promo_code}"}, {"{discount_value}"}
            </small>
          </div>
          <div className="col-12 d-flex flex-wrap gap-3 align-items-center">
            <label className="form-check d-inline-flex align-items-center mb-0">
              <input
                type="checkbox"
                className="form-check-input"
                checked={campaignForm.run_now}
                onChange={(event) =>
                  setCampaignForm((prev) => ({ ...prev, run_now: event.target.checked }))
                }
              />
              <span className="ms-1">Run immediately</span>
            </label>
            <button type="submit" className="btn btn-primary" disabled={savingCampaign}>
              <Save size={16} className="me-1" />
              {savingCampaign ? "Saving..." : "Create Campaign"}
            </button>
          </div>
        </form>

        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Channel</th>
                <th>Audience Rule</th>
                <th>Delivery</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {campaigns.map((campaign) => (
                <tr key={campaign.id}>
                  <td>
                    <div className="fw-semibold">{campaign.name}</div>
                    <small className="text-muted">Promo: {campaign.promo_code || "None"}</small>
                  </td>
                  <td>{campaign.delivery_channel}</td>
                  <td>
                    <div>Min days: {campaign.min_days_since_booking || 0}</div>
                    <small className="text-muted">Target movie id: {campaign.target_movie_id || "All"}</small>
                  </td>
                  <td>
                    <div>Sent: {campaign.sent_count || 0}</div>
                    <small className="text-muted">Failed: {campaign.failed_count || 0}</small>
                  </td>
                  <td>
                    <div className="d-flex flex-column gap-1">
                      <span className={`vendor-rule-status ${campaign.status === "COMPLETED" ? "active" : "inactive"}`}>
                        {campaign.status}
                      </span>
                      <small className="text-muted d-inline-flex align-items-center gap-1">
                        <Clock3 size={12} />
                        {campaign.scheduled_at ? formatShortDate(campaign.scheduled_at) : "No schedule"}
                      </small>
                      <select
                        className="form-select form-select-sm"
                        value={campaign.status}
                        onChange={(event) =>
                          handleCampaignStatusChange(campaign.id, event.target.value)
                        }
                      >
                        <option value="DRAFT">DRAFT</option>
                        <option value="SCHEDULED">SCHEDULED</option>
                        <option value="COMPLETED">COMPLETED</option>
                      </select>
                    </div>
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-sm btn-success"
                      onClick={() => handleRunCampaign(campaign.id)}
                      disabled={runningCampaignId === campaign.id}
                    >
                      <Play size={14} className="me-1" />
                      {runningCampaignId === campaign.id ? "Running..." : "Run"}
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && campaigns.length === 0 ? (
                <tr>
                  <td colSpan="6">No campaigns yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
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

function toDateTimeLocalValue(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  const localDate = new Date(date.getTime() - offsetMs);
  return localDate.toISOString().slice(0, 16);
}

function formatShortDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString();
}
