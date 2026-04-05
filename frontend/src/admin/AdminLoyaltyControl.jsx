import { useEffect, useMemo, useState } from "react";
import AdminPageHeader from "./components/AdminPageHeader";
import {
  createAdminLoyaltyPromotion,
  createAdminLoyaltyReward,
  deleteAdminLoyaltyPromotion,
  deleteAdminLoyaltyReward,
  fetchAdminLoyaltyControls,
  updateAdminLoyaltyPromotion,
  updateAdminLoyaltyReward,
  updateAdminLoyaltyRule,
} from "../lib/catalogApi";

const REWARD_TYPES = ["DISCOUNT", "FREE_TICKET", "CASHBACK"];
const PROMO_TYPES = ["FESTIVAL", "DAILY", "WEEKLY", "REFERRAL"];

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

export default function AdminLoyaltyControl() {
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
      const data = await fetchAdminLoyaltyControls();
      setRule(data?.rule || null);
      setRewards(Array.isArray(data?.rewards) ? data.rewards : []);
      setPromotions(Array.isArray(data?.promotions) ? data.promotions : []);
    } catch (err) {
      setError(err.message || "Unable to load loyalty controls.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSaveRule = async () => {
    if (!rule || savingRule) return;
    setSavingRule(true);
    setError("");
    setNotice("");
    try {
      const payload = {
        is_active: Boolean(rule.is_active),
        points_per_currency_unit: Number(rule.points_per_currency_unit || 0),
        redemption_value_per_point: Number(rule.redemption_value_per_point || 0),
        first_booking_bonus: Number(rule.first_booking_bonus || 0),
        points_expiry_months: Number(rule.points_expiry_months || 0),
        tier_silver_threshold: Number(rule.tier_silver_threshold || 0),
        tier_gold_threshold: Number(rule.tier_gold_threshold || 0),
        tier_platinum_threshold: Number(rule.tier_platinum_threshold || 0),
        referral_bonus_points: Number(rule.referral_bonus_points || 0),
      };
      const updated = await updateAdminLoyaltyRule(payload);
      setRule(updated || rule);
      setNotice("Loyalty rule updated.");
    } catch (err) {
      setError(err.message || "Unable to update loyalty rule.");
    } finally {
      setSavingRule(false);
    }
  };

  const handleRewardSubmit = async (event) => {
    event.preventDefault();
    if (savingReward) return;

    setSavingReward(true);
    setError("");
    setNotice("");

    try {
      const payload = {
        title: rewardForm.title,
        description: rewardForm.description,
        reward_type: rewardForm.reward_type,
        points_required: Number(rewardForm.points_required || 0),
        discount_amount: Number(rewardForm.discount_amount || 0),
        discount_percent:
          rewardForm.discount_percent === "" ? null : Number(rewardForm.discount_percent),
        max_discount_amount:
          rewardForm.max_discount_amount === ""
            ? null
            : Number(rewardForm.max_discount_amount),
        stock_limit: rewardForm.stock_limit === "" ? null : Number(rewardForm.stock_limit),
        expiry_date: rewardForm.expiry_date || null,
        is_active: Boolean(rewardForm.is_active),
        is_stackable_with_coupon: Boolean(rewardForm.is_stackable_with_coupon),
      };

      if (editingRewardId) {
        await updateAdminLoyaltyReward(editingRewardId, payload);
        setNotice("Reward updated.");
      } else {
        await createAdminLoyaltyReward(payload);
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

  const handleEditReward = (item) => {
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

  const handleDeleteReward = async (item) => {
    if (!item?.id) return;
    if (!window.confirm(`Delete reward ${item.title}?`)) return;

    setError("");
    setNotice("");
    try {
      await deleteAdminLoyaltyReward(item.id);
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
    if (savingPromotion) return;

    setSavingPromotion(true);
    setError("");
    setNotice("");

    try {
      const payload = {
        title: promotionForm.title,
        description: promotionForm.description,
        promo_type: promotionForm.promo_type,
        trigger_code: promotionForm.trigger_code || null,
        bonus_multiplier: Number(promotionForm.bonus_multiplier || 1),
        bonus_flat_points: Number(promotionForm.bonus_flat_points || 0),
        stackable: Boolean(promotionForm.stackable),
        starts_at: promotionForm.starts_at || null,
        ends_at: promotionForm.ends_at || null,
        is_active: Boolean(promotionForm.is_active),
      };

      if (editingPromotionId) {
        await updateAdminLoyaltyPromotion(editingPromotionId, payload);
        setNotice("Promotion updated.");
      } else {
        await createAdminLoyaltyPromotion(payload);
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

  const handleEditPromotion = (item) => {
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

  const handleDeletePromotion = async (item) => {
    if (!item?.id) return;
    if (!window.confirm(`Delete promotion ${item.title}?`)) return;

    setError("");
    setNotice("");
    try {
      await deleteAdminLoyaltyPromotion(item.id);
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
    <div className="d-flex flex-column gap-3">
      <AdminPageHeader
        title="Loyalty Governance"
        subtitle="Control global earning, redemption rewards, and promotions for every customer."
      />

      <section className="admin-card">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <h5 className="mb-0">Global Rule</h5>
          <div className="small text-muted">Rewards: {activeRewards} active | Promotions: {activePromotions} active</div>
        </div>

        {error ? <div className="alert alert-danger">{error}</div> : null}
        {notice ? <div className="alert alert-success">{notice}</div> : null}
        {loading ? <div className="text-muted">Loading loyalty controls...</div> : null}

        {rule ? (
          <div className="row g-2">
            <FieldNumber
              label="Points per Currency Unit"
              value={rule.points_per_currency_unit}
              onChange={(value) => setRule((prev) => ({ ...prev, points_per_currency_unit: value }))}
              step="0.01"
              min="0.01"
            />
            <FieldNumber
              label="Redemption Value per Point"
              value={rule.redemption_value_per_point}
              onChange={(value) => setRule((prev) => ({ ...prev, redemption_value_per_point: value }))}
              step="0.01"
              min="0.01"
            />
            <FieldNumber
              label="First Booking Bonus"
              value={rule.first_booking_bonus}
              onChange={(value) => setRule((prev) => ({ ...prev, first_booking_bonus: value }))}
            />
            <FieldNumber
              label="Points Expiry (Months)"
              value={rule.points_expiry_months}
              onChange={(value) => setRule((prev) => ({ ...prev, points_expiry_months: value }))}
            />
            <FieldNumber
              label="Silver Threshold"
              value={rule.tier_silver_threshold}
              onChange={(value) => setRule((prev) => ({ ...prev, tier_silver_threshold: value }))}
            />
            <FieldNumber
              label="Gold Threshold"
              value={rule.tier_gold_threshold}
              onChange={(value) => setRule((prev) => ({ ...prev, tier_gold_threshold: value }))}
            />
            <FieldNumber
              label="Platinum Threshold"
              value={rule.tier_platinum_threshold}
              onChange={(value) => setRule((prev) => ({ ...prev, tier_platinum_threshold: value }))}
            />
            <FieldNumber
              label="Referral Bonus Points"
              value={rule.referral_bonus_points}
              onChange={(value) => setRule((prev) => ({ ...prev, referral_bonus_points: value }))}
            />

            <div className="col-md-4 d-flex align-items-center">
              <label className="form-check mb-0">
                <input
                  type="checkbox"
                  className="form-check-input"
                  checked={Boolean(rule.is_active)}
                  onChange={(event) =>
                    setRule((prev) => ({ ...prev, is_active: event.target.checked }))
                  }
                />
                <span className="ms-2">Loyalty program active</span>
              </label>
            </div>

            <div className="col-12">
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleSaveRule}
                disabled={savingRule}
              >
                {savingRule ? "Saving..." : "Save Global Rule"}
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <section className="admin-card">
        <h5 className="mb-3">Global Rewards</h5>
        <form className="row g-2 mb-3" onSubmit={handleRewardSubmit}>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Reward title"
              value={rewardForm.title}
              onChange={(event) => setRewardForm((prev) => ({ ...prev, title: event.target.value }))}
              required
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
              {REWARD_TYPES.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="0"
              placeholder="Points required"
              value={rewardForm.points_required}
              onChange={(event) =>
                setRewardForm((prev) => ({ ...prev, points_required: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="0"
              step="0.01"
              placeholder="Discount amount"
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
              type="number"
              min="0"
              step="0.01"
              placeholder="Discount %"
              value={rewardForm.discount_percent}
              onChange={(event) =>
                setRewardForm((prev) => ({ ...prev, discount_percent: event.target.value }))
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
              value={rewardForm.max_discount_amount}
              onChange={(event) =>
                setRewardForm((prev) => ({ ...prev, max_discount_amount: event.target.value }))
              }
            />
          </div>
          <div className="col-md-2">
            <input
              className="form-control"
              type="number"
              min="0"
              placeholder="Stock limit"
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
              <span className="ms-1">Stack with coupon</span>
            </label>
          </div>
          <div className="col-12 d-flex gap-2">
            <button className="btn btn-primary" type="submit" disabled={savingReward}>
              {savingReward ? "Saving..." : editingRewardId ? "Update Reward" : "Create Reward"}
            </button>
            {editingRewardId ? (
              <button
                type="button"
                className="btn btn-outline-light"
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

        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Points</th>
                <th>Discount</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {rewards.map((item) => (
                <tr key={item.id}>
                  <td>{item.title}</td>
                  <td>{item.reward_type}</td>
                  <td>{item.points_required || 0}</td>
                  <td>{item.discount_percent ? `${item.discount_percent}%` : `NPR ${item.discount_amount || 0}`}</td>
                  <td>{item.is_active ? "Active" : "Inactive"}</td>
                  <td className="d-flex gap-2">
                    <button type="button" className="btn btn-sm btn-outline-light" onClick={() => handleEditReward(item)}>
                      Edit
                    </button>
                    <button type="button" className="btn btn-sm btn-outline-light" onClick={() => handleDeleteReward(item)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && rewards.length === 0 ? (
                <tr>
                  <td colSpan="6">No rewards found.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="admin-card">
        <h5 className="mb-3">Global Promotions</h5>
        <form className="row g-2 mb-3" onSubmit={handlePromotionSubmit}>
          <div className="col-md-3">
            <input
              className="form-control"
              placeholder="Promotion title"
              value={promotionForm.title}
              onChange={(event) => setPromotionForm((prev) => ({ ...prev, title: event.target.value }))}
              required
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
              {PROMO_TYPES.map((item) => (
                <option key={item} value={item}>{item}</option>
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
              min="0"
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
              placeholder="Flat points"
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
            <button className="btn btn-primary" type="submit" disabled={savingPromotion}>
              {savingPromotion
                ? "Saving..."
                : editingPromotionId
                  ? "Update Promotion"
                  : "Create Promotion"}
            </button>
            {editingPromotionId ? (
              <button
                type="button"
                className="btn btn-outline-light"
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

        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Trigger</th>
                <th>Multiplier</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {promotions.map((item) => (
                <tr key={item.id}>
                  <td>{item.title}</td>
                  <td>{item.promo_type}</td>
                  <td>{item.trigger_code || "-"}</td>
                  <td>{item.bonus_multiplier || 1}</td>
                  <td>{item.is_active ? "Active" : "Inactive"}</td>
                  <td className="d-flex gap-2">
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-light"
                      onClick={() => handleEditPromotion(item)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-light"
                      onClick={() => handleDeletePromotion(item)}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
              {!loading && promotions.length === 0 ? (
                <tr>
                  <td colSpan="6">No promotions found.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function FieldNumber({ label, value, onChange, min = "0", step = "1" }) {
  return (
    <div className="col-md-3">
      <label className="form-label">{label}</label>
      <input
        className="form-control"
        type="number"
        min={min}
        step={step}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
      />
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
