import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  applyReferralLoyaltyBonus,
  fetchLoyaltyDashboard,
} from "../lib/catalogApi";
import "../css/customerPages.css";

export default function LoyaltyDashboard() {
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [referralCode, setReferralCode] = useState("");
  const [claiming, setClaiming] = useState(false);

  const loadDashboard = async (active = true) => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchLoyaltyDashboard();
      if (!active) return;
      setDashboard(data || null);
    } catch (err) {
      if (!active) return;
      setDashboard(null);
      setError(err.message || "Unable to load loyalty dashboard.");
    } finally {
      if (active) setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    loadDashboard(active);
    return () => {
      active = false;
    };
  }, []);

  const wallet = dashboard?.wallet || {};
  const summary = dashboard?.summary || {};
  const transactions = Array.isArray(dashboard?.transactions) ? dashboard.transactions : [];

  const tierLabel = useMemo(() => {
    const tier = String(wallet?.tier || "SILVER").toUpperCase();
    if (tier === "PLATINUM") return "Platinum";
    if (tier === "GOLD") return "Gold";
    return "Silver";
  }, [wallet?.tier]);

  const handleClaimReferral = async () => {
    const code = String(referralCode || "").trim().toUpperCase();
    if (!code) {
      setError("Enter a referral code first.");
      return;
    }

    setError("");
    setNotice("");
    setClaiming(true);
    try {
      const data = await applyReferralLoyaltyBonus({ referral_code: code });
      setNotice(data?.message || "Referral bonus applied.");
      await loadDashboard(true);
      setReferralCode("");
    } catch (err) {
      setError(err.message || "Unable to apply referral bonus.");
    } finally {
      setClaiming(false);
    }
  };

  return (
    <section className="wf2-customerPage">
      <div className="wf2-customerPageHead">
        <div>
          <h1>Loyalty Dashboard</h1>
          <p>Track points, tier progress, and redemption activity.</p>
        </div>
        <button
          type="button"
          className="wf2-customerPageAction"
          onClick={() => navigate("/loyalty/rewards")}
        >
          Browse Rewards
        </button>
      </div>

      <div className="wf2-customerStats">
        <div className="wf2-customerStatCard">
          <span>Available points</span>
          <strong>{Number(wallet?.available_points || 0).toLocaleString()}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Lifetime points</span>
          <strong>{Number(wallet?.lifetime_points || 0).toLocaleString()}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Tier</span>
          <strong>{tierLabel}</strong>
        </div>
      </div>

      <div className="wf2-customerStats">
        <div className="wf2-customerStatCard">
          <span>Earned</span>
          <strong>{Number(summary?.earned || 0).toLocaleString()}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Redeemed</span>
          <strong>{Number(summary?.redeemed || 0).toLocaleString()}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Pending redemptions</span>
          <strong>{Number(summary?.pending_redemptions || 0).toLocaleString()}</strong>
        </div>
      </div>

      <div className="wf2-customerTableWrap" style={{ marginBottom: 16 }}>
        <div style={{ padding: 16, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ fontWeight: 600 }}>Referral bonus</div>
          <input
            type="text"
            className="form-control"
            value={referralCode}
            onChange={(event) => setReferralCode(event.target.value)}
            placeholder="Enter referral code"
            style={{ maxWidth: 240 }}
          />
          <button
            type="button"
            className="wf2-customerPageAction"
            onClick={handleClaimReferral}
            disabled={claiming}
          >
            {claiming ? "Applying..." : "Apply"}
          </button>
        </div>
      </div>

      {error ? <div className="wf2-customerError">{error}</div> : null}
      {notice ? <div className="wf2-customerSuccess">{notice}</div> : null}

      <div className="wf2-customerTableWrap">
        <table className="wf2-customerTable">
          <thead>
            <tr>
              <th>Type</th>
              <th>Points</th>
              <th>Reference</th>
              <th>Created</th>
              <th>Expires</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx) => (
              <tr key={tx.id}>
                <td>{formatType(tx.type)}</td>
                <td>{Number(tx.points || 0).toLocaleString()}</td>
                <td>
                  {tx.reference_type}
                  {tx.reference_id ? ` #${tx.reference_id}` : ""}
                </td>
                <td>{formatDateTime(tx.created_at)}</td>
                <td>{formatDateTime(tx.expires_at)}</td>
              </tr>
            ))}
            {!loading && transactions.length === 0 ? (
              <tr>
                <td colSpan="5">No loyalty transactions yet.</td>
              </tr>
            ) : null}
            {loading ? (
              <tr>
                <td colSpan="5">Loading loyalty dashboard...</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function formatType(value) {
  const text = String(value || "").trim().replaceAll("_", " ");
  if (!text) return "-";
  return text
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatDateTime(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}
