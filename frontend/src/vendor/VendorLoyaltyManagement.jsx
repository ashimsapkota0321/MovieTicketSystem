import { useEffect, useMemo, useState } from "react";
import {
  createVendorLoyaltyPromotion,
  createVendorLoyaltyReward,
  deleteVendorLoyaltyPromotion,
  deleteVendorLoyaltyReward,
  fetchVendorLoyaltyPromotions,
  fetchVendorLoyaltyRewards,
  fetchVendorLoyaltyRule,
  updateVendorLoyaltyPromotion,
  updateVendorLoyaltyReward,
  updateVendorLoyaltyRule,
} from "../lib/catalogApi";

const rewardTypes = ["DISCOUNT", "FREE_TICKET", "CASHBACK"];
const promoTypes = ["FESTIVAL", "DAILY", "WEEKLY", "REFERRAL"];

function emptyRewardForm() {
  return {
    title: "",
    description: "",
    reward_type: "DISCOUNT",
    points_required: "",
    discount_amount: "",
    discount_percent: "",
    max_discount_amount: "",
    stock_limit: "",
    expiry_date: "",
    is_active: true,
    is_stackable_with_coupon: true,
  };
}

function emptyPromotionForm() {
  return {
    title: "",
    description: "",
    promo_type: "FESTIVAL",
    trigger_code: "",
    bonus_multiplier: "1",
    bonus_flat_points: "0",
    stackable: false,
    starts_at: "",
    ends_at: "",
    is_active: true,
  };
}

export default function VendorLoyaltyManagement() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [rule, setRule] = useState(null);
  const [savingRule, setSavingRule] = useState(false);

  const [rewards, setRewards] = useState([]);
  const [rewardForm, setRewardForm] = useState(emptyRewardForm);
  const [editingRewardId, setEditingRewardId] = useState(null);
  const [savingReward, setSavingReward] = useState(false);

  const [promotions, setPromotions] = useState([]);
  const [promotionForm, setPromotionForm] = useState(emptyPromotionForm);
  const [editingPromotionId, setEditingPromotionId] = useState(null);
  const [savingPromotion, setSavingPromotion] = useState(false);

  const activeRewards = useMemo(
    () => rewards.filter((item) => item.is_active).length,
    [rewards]
  );

  const activePromotions = useMemo(
    () => promotions.filter((item) => item.is_active).length,
    [promotions]
  );

  const loadData = async () => {
    setLoading(true);
    setError("");
    try {
      const [ruleData, rewardData, promotionData] = await Promise.all([
        fetchVendorLoyaltyRule(),
        fetchVendorLoyaltyRewards(),
        fetchVendorLoyaltyPromotions(),
      ]);
      setRule(ruleData || null);
      setRewards(Array.isArray(rewardData) ? rewardData : []);
      setPromotions(Array.isArray(promotionData) ? promotionData : []);
    } catch (err) {
      setError(err.message || "Unable to load loyalty configuration.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleRuleSave = async () => {
    if (!rule) return;
    setSavingRule(true);
    setError("");
    setNotice("");
    try {
      const data = await updateVendorLoyaltyRule({
        is_active: Boolean(rule.is_active),
        points_per_currency_unit: Number(rule.points_per_currency_unit || 0),
        first_booking_bonus: Number(rule.first_booking_bonus || 0),
        bonus_multiplier: Number(rule.bonus_multiplier || 1),
      });
      setRule(data || rule);
      setNotice("Loyalty earning rule updated.");
    } catch (err) {
      setError(err.message || "Unable to update vendor loyalty rule.");
    } finally {
      setSavingRule(false);
    }
  };

  const handleRewardSubmit = async (event) => {
    event.preventDefault();
    setSavingReward(true);
    setError("");
    setNotice("");

    try {
      const payload = {
        ...rewardForm,
        points_required: Number(rewardForm.points_required || 0),
        discount_amount: Number(rewardForm.discount_amount || 0),
        discount_percent: rewardForm.discount_percent === "" ? null : Number(rewardForm.discount_percent),
        max_discount_amount:
          rewardForm.max_discount_amount === "" ? null : Number(rewardForm.max_discount_amount),
        stock_limit: rewardForm.stock_limit === "" ? null : Number(rewardForm.stock_limit),
        expiry_date: rewardForm.expiry_date || null,
      };

      if (editingRewardId) {
        await updateVendorLoyaltyReward(editingRewardId, payload);
        setNotice("Reward updated.");
      } else {
        await createVendorLoyaltyReward(payload);
        setNotice("Reward created.");
      }
      setEditingRewardId(null);
      setRewardForm(emptyRewardForm());
      await loadData();
    } catch (err) {
      setError(err.message || "Unable to save reward.");
    } finally {
      setSavingReward(false);
    }
  };

  const editReward = (item) => {
    setEditingRewardId(item.id);
    setRewardForm({
      title: item.title || "",
      description: item.description || "",
      reward_type: item.reward_type || "DISCOUNT",
      points_required: String(item.points_required ?? ""),
      discount_amount: String(item.discount_amount ?? ""),
      discount_percent: item.discount_percent == null ? "" : String(item.discount_percent),
      max_discount_amount:
        item.max_discount_amount == null ? "" : String(item.max_discount_amount),
      stock_limit: item.stock_limit == null ? "" : String(item.stock_limit),
      expiry_date: toDateTimeLocal(item.expiry_date),
      is_active: Boolean(item.is_active),
      is_stackable_with_coupon: Boolean(item.is_stackable_with_coupon),
    });
  };

  const deleteReward = async (item) => {
    if (!window.confirm(`Delete reward ${item.title}?`)) return;
    setError("");
    setNotice("");
    try {
      await deleteVendorLoyaltyReward(item.id);
      if (editingRewardId === item.id) {
        setEditingRewardId(null);
        setRewardForm(emptyRewardForm());
      }
      setNotice("Reward deleted.");
      await loadData();
    } catch (err) {
      setError(err.message || "Unable to delete reward.");
    }
  };

  const handlePromotionSubmit = async (event) => {
    event.preventDefault();
    setSavingPromotion(true);
    setError("");
    setNotice("");

    try {
      const payload = {
        ...promotionForm,
        bonus_multiplier: Number(promotionForm.bonus_multiplier || 1),
        bonus_flat_points: Number(promotionForm.bonus_flat_points || 0),
        starts_at: promotionForm.starts_at || null,
        ends_at: promotionForm.ends_at || null,
      };

      if (editingPromotionId) {
        await updateVendorLoyaltyPromotion(editingPromotionId, payload);
        setNotice("Promotion updated.");
      } else {
        await createVendorLoyaltyPromotion(payload);
        setNotice("Promotion created.");
      }
      setEditingPromotionId(null);
      setPromotionForm(emptyPromotionForm());
      await loadData();
    } catch (err) {
      setError(err.message || "Unable to save promotion.");
    } finally {
      setSavingPromotion(false);
    }
  };

  const editPromotion = (item) => {
    setEditingPromotionId(item.id);
    setPromotionForm({
      title: item.title || "",
      description: item.description || "",
      promo_type: item.promo_type || "FESTIVAL",
      trigger_code: item.trigger_code || "",
      bonus_multiplier: String(item.bonus_multiplier ?? "1"),
      bonus_flat_points: String(item.bonus_flat_points ?? "0"),
      stackable: Boolean(item.stackable),
      starts_at: toDateTimeLocal(item.starts_at),
      ends_at: toDateTimeLocal(item.ends_at),
      is_active: Boolean(item.is_active),
    });
  };

  const deletePromotion = async (item) => {
    if (!window.confirm(`Delete promotion ${item.title}?`)) return;
    setError("");
    setNotice("");
    try {
      await deleteVendorLoyaltyPromotion(item.id);
      if (editingPromotionId === item.id) {
        setEditingPromotionId(null);
        setPromotionForm(emptyPromotionForm());
      }
      setNotice("Promotion deleted.");
      await loadData();
    } catch (err) {
      setError(err.message || "Unable to delete promotion.");
    }
  };

  return (
    <div className="vendor-dashboard">
      <div className="vendor-card mb-3">
        <div className="vendor-card-header">
          <div>
            <h3>Loyalty Engine</h3>
            <p>Configure earning ratio, custom rewards, and promotional bonus campaigns.</p>
          </div>
          <div className="vendor-kpi-grid" style={{ display: "flex", gap: 12 }}>
            <div className="vendor-kpi-card">
              <small>Active Rewards</small>
              <strong>{activeRewards}</strong>
            </div>
            <div className="vendor-kpi-card">
              <small>Active Promotions</small>
              <strong>{activePromotions}</strong>
            </div>
          </div>
        </div>

        {error ? <div className="alert alert-danger">{error}</div> : null}
        {notice ? <div className="alert alert-success">{notice}</div> : null}
        {loading ? <div className="text-muted">Loading loyalty settings...</div> : null}

        {rule ? (
          <div className="row g-2 mb-3">
            <div className="col-md-3">
              <label className="form-label">Points per NPR unit</label>
              <input
                className="form-control"
                type="number"
                min="0.01"
                step="0.01"
                value={rule.points_per_currency_unit ?? ""}
                onChange={(event) =>
                  setRule((prev) => ({ ...prev, points_per_currency_unit: event.target.value }))
                }
              />
            </div>
            <div className="col-md-3">
              <label className="form-label">First booking bonus</label>
              <input
                className="form-control"
                type="number"
                min="0"
                value={rule.first_booking_bonus ?? ""}
                onChange={(event) =>
                  setRule((prev) => ({ ...prev, first_booking_bonus: event.target.value }))
                }
              />
            </div>
            <div className="col-md-3">
              <label className="form-label">Bonus multiplier</label>
              <input
                className="form-control"
                type="number"
                min="1"
                step="0.01"
                value={rule.bonus_multiplier ?? "1"}
                onChange={(event) =>
                  setRule((prev) => ({ ...prev, bonus_multiplier: event.target.value }))
                }
              />
            </div>
            <div className="col-md-3 d-flex align-items-end">
              <div className="form-check me-3">
                <input
                  type="checkbox"
                  className="form-check-input"
                  checked={Boolean(rule.is_active)}
                  onChange={(event) =>
                    setRule((prev) => ({ ...prev, is_active: event.target.checked }))
                  }
                />
                <label className="form-check-label">Active</label>
              </div>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleRuleSave}
                disabled={savingRule}
              >
                {savingRule ? "Saving..." : "Save Rule"}
              </button>
            </div>
          </div>
        ) : null}
      </div>

      <section className="vendor-card mb-3">
        <div className="vendor-card-header">
          <div>
            <h3>Rewards Catalog</h3>
            <p>Create discount, cashback, or free ticket rewards.</p>
          </div>
        </div>

        <form className="row g-2 mb-3" onSubmit={handleRewardSubmit}>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Reward title"
              value={rewardForm.title}
              onChange={(event) => setRewardForm((prev) => ({ ...prev, title: event.target.value }))}
            />
          </div>
          <div className="col-md-2">
            <select
              className="form-select"
              value={rewardForm.reward_type}
              onChange={(event) =>
                setRewardForm((prev) => ({ ...prev, reward_type: event.target.value }))
              }
            >
              {rewardTypes.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              placeholder="Points"
              type="number"
              min="0"
              value={rewardForm.points_required}
              onChange={(event) =>
                setRewardForm((prev) => ({ ...prev, points_required: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              placeholder="Discount amount"
              type="number"
              min="0"
              step="0.01"
              value={rewardForm.discount_amount}
              onChange={(event) =>
                setRewardForm((prev) => ({ ...prev, discount_amount: event.target.value }))
              }
            />
          </div>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Description"
              value={rewardForm.description}
              onChange={(event) =>
                setRewardForm((prev) => ({ ...prev, description: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              placeholder="Discount %"
              type="number"
              min="0"
              step="0.01"
              value={rewardForm.discount_percent}
              onChange={(event) =>
                setRewardForm((prev) => ({ ...prev, discount_percent: event.target.value }))
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
              value={rewardForm.max_discount_amount}
              onChange={(event) =>
                setRewardForm((prev) => ({ ...prev, max_discount_amount: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              placeholder="Stock"
              type="number"
              min="0"
              value={rewardForm.stock_limit}
              onChange={(event) =>
                setRewardForm((prev) => ({ ...prev, stock_limit: event.target.value }))
              }
            />
          </div>
          <div className="col-md-3">
            <input
              className="form-control"
              type="datetime-local"
              value={rewardForm.expiry_date}
              onChange={(event) =>
                setRewardForm((prev) => ({ ...prev, expiry_date: event.target.value }))
              }
            />
          </div>
          <div className="col-md-3 d-flex align-items-center gap-3">
            <label className="form-check mb-0">
              <input
                type="checkbox"
                className="form-check-input"
                checked={rewardForm.is_active}
                onChange={(event) =>
                  setRewardForm((prev) => ({ ...prev, is_active: event.target.checked }))
                }
              />
              <span className="ms-1">Active</span>
            </label>
            <label className="form-check mb-0">
              <input
                type="checkbox"
                className="form-check-input"
                checked={rewardForm.is_stackable_with_coupon}
                onChange={(event) =>
                  setRewardForm((prev) => ({ ...prev, is_stackable_with_coupon: event.target.checked }))
                }
              />
              <span className="ms-1">Stackable with coupon</span>
            </label>
          </div>
          <div className="col-12 d-flex gap-2">
            <button type="submit" className="btn btn-primary" disabled={savingReward}>
              {savingReward ? "Saving..." : editingRewardId ? "Update Reward" : "Create Reward"}
            </button>
            {editingRewardId ? (
              <button
                type="button"
                className="btn btn-outline-secondary"
                onClick={() => {
                  setEditingRewardId(null);
                  setRewardForm(emptyRewardForm());
                }}
              >
                Cancel
              </button>
            ) : null}
          </div>
        </form>

        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Reward</th>
                <th>Type</th>
                <th>Points</th>
                <th>Usage</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rewards.map((item) => (
                <tr key={item.id}>
                  <td>
                    <div className="fw-semibold">{item.title}</div>
                    <small className="text-muted">{item.description || "-"}</small>
                  </td>
                  <td>{item.reward_type}</td>
                  <td>{item.points_required}</td>
                  <td>
                    {item.redeemed_count}
                    {item.stock_limit != null ? ` / ${item.stock_limit}` : ""}
                  </td>
                  <td>{item.is_active ? "ACTIVE" : "INACTIVE"}</td>
                  <td>
                    <div className="d-flex gap-2">
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-primary"
                        onClick={() => editReward(item)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-danger"
                        onClick={() => deleteReward(item)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && rewards.length === 0 ? (
                <tr>
                  <td colSpan="6">No rewards created yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Bonus Promotions</h3>
            <p>Create festival and referral bonus point campaigns.</p>
          </div>
        </div>

        <form className="row g-2 mb-3" onSubmit={handlePromotionSubmit}>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Promotion title"
              value={promotionForm.title}
              onChange={(event) =>
                setPromotionForm((prev) => ({ ...prev, title: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <select
              className="form-select"
              value={promotionForm.promo_type}
              onChange={(event) =>
                setPromotionForm((prev) => ({ ...prev, promo_type: event.target.value }))
              }
            >
              {promoTypes.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              placeholder="Trigger code"
              value={promotionForm.trigger_code}
              onChange={(event) =>
                setPromotionForm((prev) => ({ ...prev, trigger_code: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="1"
              step="0.01"
              placeholder="Multiplier"
              value={promotionForm.bonus_multiplier}
              onChange={(event) =>
                setPromotionForm((prev) => ({ ...prev, bonus_multiplier: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="0"
              placeholder="Flat bonus"
              value={promotionForm.bonus_flat_points}
              onChange={(event) =>
                setPromotionForm((prev) => ({ ...prev, bonus_flat_points: event.target.value }))
              }
            />
          </div>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Description"
              value={promotionForm.description}
              onChange={(event) =>
                setPromotionForm((prev) => ({ ...prev, description: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="datetime-local"
              value={promotionForm.starts_at}
              onChange={(event) =>
                setPromotionForm((prev) => ({ ...prev, starts_at: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="datetime-local"
              value={promotionForm.ends_at}
              onChange={(event) =>
                setPromotionForm((prev) => ({ ...prev, ends_at: event.target.value }))
              }
            />
          </div>
          <div className="col-md-3 d-flex align-items-center gap-3">
            <label className="form-check mb-0">
              <input
                type="checkbox"
                className="form-check-input"
                checked={promotionForm.stackable}
                onChange={(event) =>
                  setPromotionForm((prev) => ({ ...prev, stackable: event.target.checked }))
                }
              />
              <span className="ms-1">Stackable</span>
            </label>
            <label className="form-check mb-0">
              <input
                type="checkbox"
                className="form-check-input"
                checked={promotionForm.is_active}
                onChange={(event) =>
                  setPromotionForm((prev) => ({ ...prev, is_active: event.target.checked }))
                }
              />
              <span className="ms-1">Active</span>
            </label>
          </div>
          <div className="col-12 d-flex gap-2">
            <button type="submit" className="btn btn-primary" disabled={savingPromotion}>
              {savingPromotion
                ? "Saving..."
                : editingPromotionId
                  ? "Update Promotion"
                  : "Create Promotion"}
            </button>
            {editingPromotionId ? (
              <button
                type="button"
                className="btn btn-outline-secondary"
                onClick={() => {
                  setEditingPromotionId(null);
                  setPromotionForm(emptyPromotionForm());
                }}
              >
                Cancel
              </button>
            ) : null}
          </div>
        </form>

        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Promotion</th>
                <th>Type</th>
                <th>Bonus</th>
                <th>Window</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {promotions.map((item) => (
                <tr key={item.id}>
                  <td>
                    <div className="fw-semibold">{item.title}</div>
                    <small className="text-muted">Trigger: {item.trigger_code || "Always"}</small>
                  </td>
                  <td>{item.promo_type}</td>
                  <td>
                    x{item.bonus_multiplier} + {item.bonus_flat_points} pts
                  </td>
                  <td>
                    <div>{formatDate(item.starts_at)}</div>
                    <small className="text-muted">to {formatDate(item.ends_at)}</small>
                  </td>
                  <td>{item.is_active ? "ACTIVE" : "INACTIVE"}</td>
                  <td>
                    <div className="d-flex gap-2">
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-primary"
                        onClick={() => editPromotion(item)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-danger"
                        onClick={() => deletePromotion(item)}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && promotions.length === 0 ? (
                <tr>
                  <td colSpan="6">No promotions created yet.</td>
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
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  const hour = String(parsed.getHours()).padStart(2, "0");
  const minute = String(parsed.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
}

function formatDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}
