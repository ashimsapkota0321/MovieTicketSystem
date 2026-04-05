import { useEffect, useMemo, useState } from "react";
import AdminPageHeader from "./components/AdminPageHeader";
import {
  createAdminSubscriptionPlan,
  deleteAdminSubscriptionPlan,
  fetchAdminSubscriptionPlans,
  updateAdminSubscriptionPlan,
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

export default function AdminSubscriptionControl() {
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
      const data = await fetchAdminSubscriptionPlans({ include_inactive: true });
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

  const normalizePayload = () => ({
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
  });

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (saving) return;

    setSaving(true);
    setError("");
    setNotice("");
    try {
      const payload = normalizePayload();
      if (editingPlanId) {
        await updateAdminSubscriptionPlan(editingPlanId, payload);
        setNotice("Subscription plan updated.");
      } else {
        await createAdminSubscriptionPlan(payload);
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
      await deleteAdminSubscriptionPlan(plan.id);
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
    <div className="d-flex flex-column gap-3">
      <AdminPageHeader
        title="Subscription Governance"
        subtitle="Define globally available membership plans and pricing privileges."
      />

      <section className="admin-card">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <div className="text-muted small">
            Total plans: {plans.length} | Active: {activePlanCount}
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
              onChange={(event) =>
                setForm((prev) => ({ ...prev, code: event.target.value.toUpperCase() }))
              }
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
              onChange={(event) =>
                setForm((prev) => ({ ...prev, duration_days: event.target.value }))
              }
            />
          </div>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Description"
              value={form.description}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, description: event.target.value }))
              }
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
              onChange={(event) =>
                setForm((prev) => ({ ...prev, discount_type: event.target.value }))
              }
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
              onChange={(event) =>
                setForm((prev) => ({ ...prev, discount_value: event.target.value }))
              }
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
              onChange={(event) =>
                setForm((prev) => ({ ...prev, max_discount_amount: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="0"
              placeholder="Free tickets"
              value={form.free_tickets_total}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, free_tickets_total: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="0"
              placeholder="Early access hours"
              value={form.early_access_hours}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, early_access_hours: event.target.value }))
              }
            />
          </div>

          <div className="col-md-12 d-flex flex-wrap gap-3 align-items-center">
            <label className="form-check mb-0">
              <input
                type="checkbox"
                className="form-check-input"
                checked={form.is_public}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, is_public: event.target.checked }))
                }
              />
              <span className="ms-1">Public</span>
            </label>
            <label className="form-check mb-0">
              <input
                type="checkbox"
                className="form-check-input"
                checked={form.is_active}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, is_active: event.target.checked }))
                }
              />
              <span className="ms-1">Active</span>
            </label>
            <label className="form-check mb-0">
              <input
                type="checkbox"
                className="form-check-input"
                checked={form.allow_multiple_active}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, allow_multiple_active: event.target.checked }))
                }
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
                className="btn btn-outline-light"
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

      <section className="admin-card">
        <h5 className="mb-3">Global Plan Catalog</h5>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Name</th>
                <th>Tier</th>
                <th>Price</th>
                <th>Discount</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {plans.map((plan) => (
                <tr key={plan.id}>
                  <td>{plan.code}</td>
                  <td>{plan.name}</td>
                  <td>{plan.tier}</td>
                  <td>NPR {plan.price ?? 0}</td>
                  <td>{plan.discount_type} {plan.discount_value ?? 0}</td>
                  <td>{plan.is_active ? "Active" : "Inactive"}</td>
                  <td className="d-flex gap-2">
                    <button
                      type="button"
                      className="btn btn-outline-light btn-sm"
                      onClick={() => handleEdit(plan)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn btn-outline-light btn-sm"
                      onClick={() => handleDelete(plan)}
                    >
                      Disable
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && plans.length === 0 ? (
                <tr>
                  <td colSpan="7">No subscription plans found.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
