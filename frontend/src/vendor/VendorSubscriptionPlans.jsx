import { useEffect, useMemo, useState } from "react";
import {
  createVendorSubscriptionPlan,
  deleteVendorSubscriptionPlan,
  fetchVendorSubscriptionPlans,
  updateVendorSubscriptionPlan,
} from "../lib/catalogApi";

const TIER_OPTIONS = ["SILVER", "GOLD", "PLATINUM"];
const DISCOUNT_TYPE_OPTIONS = ["NONE", "PERCENTAGE", "FIXED"];

function emptyForm() {
  return {
    code: "",
    name: "",
    description: "",
    tier: "SILVER",
    duration_days: "30",
    price: "",
    currency: "NPR",
    discount_type: "NONE",
    discount_value: "0",
    max_discount_amount: "",
    free_tickets_total: "0",
    early_access_hours: "0",
    priority: "100",
    is_public: true,
    is_active: true,
    allow_multiple_active: false,
    is_stackable_with_coupon: true,
    is_stackable_with_loyalty: true,
    is_stackable_with_referral_wallet: true,
  };
}

export default function VendorSubscriptionPlans() {
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingPlanId, setEditingPlanId] = useState(null);
  const [form, setForm] = useState(emptyForm);

  const activePlanCount = useMemo(
    () => plans.filter((item) => item.is_active).length,
    [plans]
  );

  const loadPlans = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchVendorSubscriptionPlans();
      setPlans(Array.isArray(data) ? data : []);
    } catch (err) {
      setPlans([]);
      setError(err.message || "Unable to load subscription plans.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPlans();
  }, []);

  const normalizePayload = () => {
    const payload = {
      code: String(form.code || "").trim().toUpperCase(),
      name: String(form.name || "").trim(),
      description: String(form.description || "").trim(),
      tier: form.tier,
      duration_days: Number(form.duration_days || 0),
      price: Number(form.price || 0),
      currency: String(form.currency || "NPR").trim().toUpperCase(),
      discount_type: form.discount_type,
      discount_value: Number(form.discount_value || 0),
      max_discount_amount:
        String(form.max_discount_amount || "").trim() === ""
          ? null
          : Number(form.max_discount_amount),
      free_tickets_total: Number(form.free_tickets_total || 0),
      early_access_hours: Number(form.early_access_hours || 0),
      priority: Number(form.priority || 100),
      is_public: Boolean(form.is_public),
      is_active: Boolean(form.is_active),
      allow_multiple_active: Boolean(form.allow_multiple_active),
      is_stackable_with_coupon: Boolean(form.is_stackable_with_coupon),
      is_stackable_with_loyalty: Boolean(form.is_stackable_with_loyalty),
      is_stackable_with_referral_wallet: Boolean(form.is_stackable_with_referral_wallet),
    };
    return payload;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (saving) return;

    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payload = normalizePayload();
      if (editingPlanId) {
        await updateVendorSubscriptionPlan(editingPlanId, payload);
        setNotice("Subscription plan updated.");
      } else {
        await createVendorSubscriptionPlan(payload);
        setNotice("Subscription plan created.");
      }
      setEditingPlanId(null);
      setForm(emptyForm());
      await loadPlans();
    } catch (err) {
      setError(err.message || "Unable to save subscription plan.");
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (plan) => {
    setEditingPlanId(plan.id);
    setForm({
      code: plan.code || "",
      name: plan.name || "",
      description: plan.description || "",
      tier: plan.tier || "SILVER",
      duration_days: String(plan.duration_days ?? 30),
      price: String(plan.price ?? ""),
      currency: plan.currency || "NPR",
      discount_type: plan.discount_type || "NONE",
      discount_value: String(plan.discount_value ?? 0),
      max_discount_amount:
        plan.max_discount_amount == null ? "" : String(plan.max_discount_amount),
      free_tickets_total: String(plan.free_tickets_total ?? 0),
      early_access_hours: String(plan.early_access_hours ?? 0),
      priority: String(plan.priority ?? 100),
      is_public: Boolean(plan.is_public),
      is_active: Boolean(plan.is_active),
      allow_multiple_active: Boolean(plan.allow_multiple_active),
      is_stackable_with_coupon: Boolean(plan.is_stackable_with_coupon),
      is_stackable_with_loyalty: Boolean(plan.is_stackable_with_loyalty),
      is_stackable_with_referral_wallet: Boolean(plan.is_stackable_with_referral_wallet),
    });
  };

  const handleDelete = async (plan) => {
    if (!plan?.id) return;
    if (!window.confirm(`Disable subscription plan ${plan.name}?`)) return;

    setError("");
    setNotice("");
    try {
      await deleteVendorSubscriptionPlan(plan.id);
      setNotice("Subscription plan disabled.");
      if (editingPlanId === plan.id) {
        setEditingPlanId(null);
        setForm(emptyForm());
      }
      await loadPlans();
    } catch (err) {
      setError(err.message || "Unable to disable subscription plan.");
    }
  };

  return (
    <div className="vendor-dashboard">
      <section className="vendor-card mb-3">
        <div className="vendor-card-header">
          <div>
            <h3>Membership Plans</h3>
            <p>Create and manage subscription plans for your cinema customers.</p>
          </div>
          <div className="vendor-kpi-grid" style={{ display: "flex", gap: 12 }}>
            <div className="vendor-kpi-card">
              <small>Total Plans</small>
              <strong>{plans.length}</strong>
            </div>
            <div className="vendor-kpi-card">
              <small>Active Plans</small>
              <strong>{activePlanCount}</strong>
            </div>
          </div>
        </div>

        {error ? <div className="alert alert-danger">{error}</div> : null}
        {notice ? <div className="alert alert-success">{notice}</div> : null}
        {loading ? <div className="text-muted">Loading subscription plans...</div> : null}

        <form className="row g-2" onSubmit={handleSubmit}>
          <div className="col-md-2">
            <input
              className="form-control"
              placeholder="Code"
              value={form.code}
              onChange={(event) => setForm((prev) => ({ ...prev, code: event.target.value.toUpperCase() }))}
              required
            />
          </div>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Plan name"
              value={form.name}
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
              required
            />
          </div>
          <div className="col-md-2">
            <select
              className="form-select"
              value={form.tier}
              onChange={(event) => setForm((prev) => ({ ...prev, tier: event.target.value }))}
            >
              {TIER_OPTIONS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="1"
              placeholder="Duration days"
              value={form.duration_days}
              onChange={(event) => setForm((prev) => ({ ...prev, duration_days: event.target.value }))}
            />
          </div>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Description"
              value={form.description}
              onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
            />
          </div>

          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="0"
              step="0.01"
              placeholder="Price"
              value={form.price}
              onChange={(event) => setForm((prev) => ({ ...prev, price: event.target.value }))}
              required
            />
          </div>
          <div className="col-md-2">
            <select
              className="form-select"
              value={form.discount_type}
              onChange={(event) => setForm((prev) => ({ ...prev, discount_type: event.target.value }))}
            >
              {DISCOUNT_TYPE_OPTIONS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="0"
              step="0.01"
              placeholder="Discount value"
              value={form.discount_value}
              onChange={(event) => setForm((prev) => ({ ...prev, discount_value: event.target.value }))}
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="0"
              step="0.01"
              placeholder="Max discount"
              value={form.max_discount_amount}
              onChange={(event) => setForm((prev) => ({ ...prev, max_discount_amount: event.target.value }))}
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="0"
              placeholder="Free tickets"
              value={form.free_tickets_total}
              onChange={(event) => setForm((prev) => ({ ...prev, free_tickets_total: event.target.value }))}
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="0"
              placeholder="Early access hours"
              value={form.early_access_hours}
              onChange={(event) => setForm((prev) => ({ ...prev, early_access_hours: event.target.value }))}
            />
          </div>

          <div className="col-md-12 d-flex flex-wrap gap-3 align-items-center">
            <label className="form-check mb-0">
              <input
                type="checkbox"
                className="form-check-input"
                checked={form.is_public}
                onChange={(event) => setForm((prev) => ({ ...prev, is_public: event.target.checked }))}
              />
              <span className="ms-1">Public</span>
            </label>
            <label className="form-check mb-0">
              <input
                type="checkbox"
                className="form-check-input"
                checked={form.is_active}
                onChange={(event) => setForm((prev) => ({ ...prev, is_active: event.target.checked }))}
              />
              <span className="ms-1">Active</span>
            </label>
            <label className="form-check mb-0">
              <input
                type="checkbox"
                className="form-check-input"
                checked={form.allow_multiple_active}
                onChange={(event) => setForm((prev) => ({ ...prev, allow_multiple_active: event.target.checked }))}
              />
              <span className="ms-1">Allow multiple active</span>
            </label>
          </div>

          <div className="col-12 d-flex gap-2">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? "Saving..." : editingPlanId ? "Update Plan" : "Create Plan"}
            </button>
            {editingPlanId ? (
              <button
                type="button"
                className="btn btn-outline-secondary"
                onClick={() => {
                  setEditingPlanId(null);
                  setForm(emptyForm());
                }}
              >
                Cancel
              </button>
            ) : null}
          </div>
        </form>
      </section>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Plan Catalog</h3>
            <p>Review all plans currently configured for your vendor account.</p>
          </div>
        </div>

        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Name</th>
                <th>Tier</th>
                <th>Price</th>
                <th>Discount</th>
                <th>Free Tickets</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {plans.map((plan) => (
                <tr key={plan.id}>
                  <td>{plan.code}</td>
                  <td>
                    <div className="fw-semibold">{plan.name}</div>
                    <small className="text-muted">{plan.description || "-"}</small>
                  </td>
                  <td>{plan.tier}</td>
                  <td>
                    {plan.currency || "NPR"} {Number(plan.price || 0).toLocaleString()}
                  </td>
                  <td>
                    {plan.discount_type === "NONE"
                      ? "-"
                      : `${plan.discount_type}: ${Number(plan.discount_value || 0).toLocaleString()}`}
                  </td>
                  <td>{Number(plan.free_tickets_total || 0).toLocaleString()}</td>
                  <td>
                    {plan.is_active ? "ACTIVE" : "INACTIVE"}
                    {plan.is_public ? " / PUBLIC" : " / PRIVATE"}
                  </td>
                  <td>
                    <div className="d-flex gap-2">
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-primary"
                        onClick={() => handleEdit(plan)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-danger"
                        onClick={() => handleDelete(plan)}
                      >
                        Disable
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && plans.length === 0 ? (
                <tr>
                  <td colSpan="8">No subscription plans created yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
