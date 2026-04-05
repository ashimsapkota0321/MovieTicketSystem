import { useEffect, useMemo, useState } from "react";
import {
  createVendorOffer,
  deleteVendorOffer,
  fetchVendorOffers,
  updateVendorOffer,
} from "../lib/catalogApi";

const OFFER_TYPES = ["PROMO", "BUNDLE", "PERK", "LOYALTY"];
const DISCOUNT_TYPES = ["NONE", "PERCENTAGE", "FIXED"];

function emptyForm() {
  return {
    title: "",
    code: "",
    description: "",
    offer_type: "PROMO",
    discount_type: "NONE",
    discount_value: "0",
    min_booking_amount: "0",
    allow_loyalty_redemption: true,
    subscriber_perk_text: "",
    starts_at: "",
    ends_at: "",
    is_active: true,
  };
}

export default function VendorOffers() {
  const [offers, setOffers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingOfferId, setEditingOfferId] = useState(null);
  const [form, setForm] = useState(emptyForm);

  const activeOfferCount = useMemo(
    () => offers.filter((item) => item.is_active).length,
    [offers]
  );

  const loadOffers = async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchVendorOffers({ include_inactive: true });
      setOffers(Array.isArray(data) ? data : []);
    } catch (err) {
      setOffers([]);
      setError(err.message || "Unable to load offers.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOffers();
  }, []);

  const normalizePayload = () => ({
    title: String(form.title || "").trim(),
    code: String(form.code || "").trim() || null,
    description: String(form.description || "").trim() || null,
    offer_type: form.offer_type,
    discount_type: form.discount_type,
    discount_value: Number(form.discount_value || 0),
    min_booking_amount: Number(form.min_booking_amount || 0),
    allow_loyalty_redemption: Boolean(form.allow_loyalty_redemption),
    subscriber_perk_text: String(form.subscriber_perk_text || "").trim() || null,
    starts_at: form.starts_at || null,
    ends_at: form.ends_at || null,
    is_active: Boolean(form.is_active),
  });

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (saving) return;

    setSaving(true);
    setError("");
    setNotice("");

    try {
      const payload = normalizePayload();
      if (editingOfferId) {
        await updateVendorOffer(editingOfferId, payload);
        setNotice("Offer updated.");
      } else {
        await createVendorOffer(payload);
        setNotice("Offer created.");
      }
      setEditingOfferId(null);
      setForm(emptyForm());
      await loadOffers();
    } catch (err) {
      setError(err.message || "Unable to save offer.");
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (offer) => {
    setEditingOfferId(offer.id);
    setForm({
      title: offer.title || "",
      code: offer.code || "",
      description: offer.description || "",
      offer_type: offer.offer_type || "PROMO",
      discount_type: offer.discount_type || "NONE",
      discount_value: String(offer.discount_value ?? 0),
      min_booking_amount: String(offer.min_booking_amount ?? 0),
      allow_loyalty_redemption: Boolean(offer.allow_loyalty_redemption),
      subscriber_perk_text: offer.subscriber_perk_text || "",
      starts_at: toDateTimeLocal(offer.starts_at),
      ends_at: toDateTimeLocal(offer.ends_at),
      is_active: Boolean(offer.is_active),
    });
  };

  const handleDelete = async (offer) => {
    if (!offer?.id) return;
    if (!window.confirm(`Disable offer ${offer.title}?`)) return;

    setError("");
    setNotice("");
    try {
      await deleteVendorOffer(offer.id);
      setNotice("Offer disabled.");
      if (editingOfferId === offer.id) {
        setEditingOfferId(null);
        setForm(emptyForm());
      }
      await loadOffers();
    } catch (err) {
      setError(err.message || "Unable to disable offer.");
    }
  };

  return (
    <div className="vendor-dashboard">
      <section className="vendor-card mb-3">
        <div className="vendor-card-header">
          <div>
            <h3>Vendor Offers</h3>
            <p>Manage promo, bundle, perk, and loyalty offers available for your cinema.</p>
          </div>
          <div className="vendor-kpi-grid" style={{ display: "flex", gap: 12 }}>
            <div className="vendor-kpi-card">
              <small>Total Offers</small>
              <strong>{offers.length}</strong>
            </div>
            <div className="vendor-kpi-card">
              <small>Active Offers</small>
              <strong>{activeOfferCount}</strong>
            </div>
          </div>
        </div>

        {error ? <div className="alert alert-danger">{error}</div> : null}
        {notice ? <div className="alert alert-success">{notice}</div> : null}
        {loading ? <div className="text-muted">Loading offers...</div> : null}

        <form className="row g-2" onSubmit={handleSubmit}>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Offer title"
              value={form.title}
              onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
              required
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              placeholder="Code (optional)"
              value={form.code}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, code: event.target.value.toUpperCase() }))
              }
            />
          </div>
          <div className="col-md-2">
            <select
              className="form-select"
              value={form.offer_type}
              onChange={(event) => setForm((prev) => ({ ...prev, offer_type: event.target.value }))}
            >
              {OFFER_TYPES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-2">
            <select
              className="form-select"
              value={form.discount_type}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, discount_type: event.target.value }))
              }
            >
              {DISCOUNT_TYPES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
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
              placeholder="Min booking amount"
              value={form.min_booking_amount}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, min_booking_amount: event.target.value }))
              }
            />
          </div>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Subscriber perk text"
              value={form.subscriber_perk_text}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, subscriber_perk_text: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="datetime-local"
              value={form.starts_at}
              onChange={(event) => setForm((prev) => ({ ...prev, starts_at: event.target.value }))}
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="datetime-local"
              value={form.ends_at}
              onChange={(event) => setForm((prev) => ({ ...prev, ends_at: event.target.value }))}
            />
          </div>
          <div className="col-md-3 d-flex align-items-center gap-3">
            <label className="form-check mb-0">
              <input
                type="checkbox"
                className="form-check-input"
                checked={form.allow_loyalty_redemption}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    allow_loyalty_redemption: event.target.checked,
                  }))
                }
              />
              <span className="ms-1">Allow loyalty redemption</span>
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
          </div>

          <div className="col-12 d-flex gap-2">
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? "Saving..." : editingOfferId ? "Update Offer" : "Create Offer"}
            </button>
            {editingOfferId ? (
              <button
                type="button"
                className="btn btn-outline-secondary"
                onClick={() => {
                  setEditingOfferId(null);
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
            <h3>Offer Catalog</h3>
            <p>Review and update all offers configured for your venue.</p>
          </div>
        </div>

        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Code</th>
                <th>Discount</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {offers.map((offer) => (
                <tr key={offer.id}>
                  <td>{offer.title}</td>
                  <td>{offer.offer_type}</td>
                  <td>{offer.code || "-"}</td>
                  <td>
                    {offer.discount_type === "PERCENTAGE"
                      ? `${offer.discount_value}%`
                      : offer.discount_type === "FIXED"
                        ? `NPR ${offer.discount_value}`
                        : "-"}
                  </td>
                  <td>{offer.is_active ? "Active" : "Inactive"}</td>
                  <td>
                    <div className="d-flex gap-2">
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => handleEdit(offer)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => handleDelete(offer)}
                      >
                        Disable
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && offers.length === 0 ? (
                <tr>
                  <td colSpan="6">No offers configured yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function toDateTimeLocal(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}
