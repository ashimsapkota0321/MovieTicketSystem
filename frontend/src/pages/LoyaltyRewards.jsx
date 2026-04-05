import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchLoyaltyRewards, redeemLoyaltyReward } from "../lib/catalogApi";
import "../css/customerPages.css";

export default function LoyaltyRewards() {
  const navigate = useNavigate();
  const [wallet, setWallet] = useState(null);
  const [rewards, setRewards] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyRewardId, setBusyRewardId] = useState(null);
  const [pointsFilter, setPointsFilter] = useState("");

  const loadRewards = async (active = true) => {
    setLoading(true);
    setError("");
    try {
      const params = {};
      if (pointsFilter) params.min_points = Number(pointsFilter || 0);
      const data = await fetchLoyaltyRewards(params);
      if (!active) return;
      setWallet(data?.wallet || null);
      setRewards(Array.isArray(data?.rewards) ? data.rewards : []);
    } catch (err) {
      if (!active) return;
      setWallet(null);
      setRewards([]);
      setError(err.message || "Unable to load rewards.");
    } finally {
      if (active) setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    loadRewards(active);
    return () => {
      active = false;
    };
  }, [pointsFilter]);

  const groupedRewards = useMemo(() => {
    const map = new Map();
    rewards.forEach((item) => {
      const key = item.vendor_name || "Global";
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(item);
    });
    return Array.from(map.entries());
  }, [rewards]);

  const handleRedeem = async (reward) => {
    const rewardId = Number(reward?.id || 0);
    if (!rewardId || busyRewardId === rewardId) return;

    if (!window.confirm(`Redeem ${reward.title} for ${reward.points_required} points?`)) {
      return;
    }

    setError("");
    setNotice("");
    setBusyRewardId(rewardId);
    try {
      const data = await redeemLoyaltyReward({ reward_id: rewardId });
      setNotice(data?.message || "Reward redeemed successfully.");
      await loadRewards(true);
    } catch (err) {
      setError(err.message || "Unable to redeem reward.");
    } finally {
      setBusyRewardId(null);
    }
  };

  return (
    <section className="wf2-customerPage">
      <div className="wf2-customerPageHead">
        <div>
          <h1>Loyalty Rewards</h1>
          <p>Redeem points for discounts, cashback, or free tickets.</p>
        </div>
        <button
          type="button"
          className="wf2-customerPageAction"
          onClick={() => navigate("/loyalty/dashboard")}
        >
          Back to Dashboard
        </button>
      </div>

      <div className="wf2-customerStats">
        <div className="wf2-customerStatCard">
          <span>Available points</span>
          <strong>{Number(wallet?.available_points || 0).toLocaleString()}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Total rewards</span>
          <strong>{Number(rewards.length || 0).toLocaleString()}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Lifetime points</span>
          <strong>{Number(wallet?.lifetime_points || 0).toLocaleString()}</strong>
        </div>
      </div>

      <div className="wf2-customerTableWrap" style={{ marginBottom: 16 }}>
        <div style={{ padding: 16, display: "flex", gap: 10, alignItems: "center" }}>
          <div style={{ fontWeight: 600 }}>Minimum points</div>
          <input
            type="number"
            min="0"
            className="form-control"
            value={pointsFilter}
            onChange={(event) => setPointsFilter(event.target.value)}
            placeholder="0"
            style={{ maxWidth: 160 }}
          />
        </div>
      </div>

      {error ? <div className="wf2-customerError">{error}</div> : null}
      {notice ? <div className="wf2-customerSuccess">{notice}</div> : null}

      {groupedRewards.map(([vendorName, items]) => (
        <div className="wf2-customerTableWrap" key={vendorName} style={{ marginBottom: 16 }}>
          <div style={{ padding: 16, fontWeight: 700 }}>{vendorName}</div>
          <table className="wf2-customerTable">
            <thead>
              <tr>
                <th>Reward</th>
                <th>Type</th>
                <th>Points</th>
                <th>Benefit</th>
                <th>Expiry</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {items.map((reward) => (
                <tr key={reward.id}>
                  <td>
                    <div style={{ fontWeight: 600 }}>{reward.title}</div>
                    <div className="text-muted small">{reward.description || "-"}</div>
                  </td>
                  <td>{reward.reward_type}</td>
                  <td>{Number(reward.points_required || 0).toLocaleString()}</td>
                  <td>{formatBenefit(reward)}</td>
                  <td>{formatDateTime(reward.expiry_date)}</td>
                  <td>
                    <button
                      type="button"
                      className="wf2-customerPageAction"
                      disabled={!reward.can_redeem || busyRewardId === reward.id}
                      onClick={() => handleRedeem(reward)}
                    >
                      {busyRewardId === reward.id ? "Redeeming..." : "Redeem"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {!loading && rewards.length === 0 ? (
        <div className="wf2-customerTableWrap">
          <div style={{ padding: 16 }}>No rewards available right now.</div>
        </div>
      ) : null}
      {loading ? (
        <div className="wf2-customerTableWrap">
          <div style={{ padding: 16 }}>Loading rewards...</div>
        </div>
      ) : null}
    </section>
  );
}

function formatBenefit(reward) {
  const amount = Number(reward?.discount_amount || 0);
  const percent = Number(reward?.discount_percent || 0);
  if (reward?.reward_type === "FREE_TICKET") return "Free ticket";
  if (percent > 0) return `${percent}% off`;
  if (amount > 0) return `NPR ${amount.toLocaleString()} off`;
  return "-";
}

function formatDateTime(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}
