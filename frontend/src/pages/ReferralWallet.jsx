import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  fetchReferralDashboard,
  fetchReferralWalletTransactions,
} from "../lib/catalogApi";
import "../css/customerPages.css";

export default function ReferralWallet() {
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadData = async (active = true) => {
    setLoading(true);
    setError("");
    try {
      const [dashboardData, transactionData] = await Promise.all([
        fetchReferralDashboard(),
        fetchReferralWalletTransactions({ limit: 80 }),
      ]);
      if (!active) return;
      setDashboard(dashboardData || null);
      setTransactions(Array.isArray(transactionData?.transactions) ? transactionData.transactions : []);
    } catch (err) {
      if (!active) return;
      setDashboard(null);
      setTransactions([]);
      setError(err.message || "Unable to load referral wallet details.");
    } finally {
      if (active) setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    loadData(active);
    return () => {
      active = false;
    };
  }, []);

  const wallet = dashboard?.wallet || {};
  const referral = dashboard?.referral || {};
  const referralSummary = referral?.summary || {};
  const rewardPolicy = referral?.reward_policy || {};
  const sentReferrals = Array.isArray(referral?.sent) ? referral.sent : [];
  const receivedReferral = referral?.received || null;

  const handleCopy = async (value, label) => {
    const text = String(value || "").trim();
    if (!text) {
      setNotice(`No ${label} available to copy.`);
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setNotice(`${label} copied.`);
    } catch {
      setNotice(`Unable to copy ${label.toLowerCase()}.`);
    }
  };

  return (
    <section className="wf2-customerPage">
      <div className="wf2-customerPageHead">
        <div>
          <h1>Referral Wallet</h1>
          <p>Share your referral code and spend earned credit during checkout.</p>
        </div>
        <button
          type="button"
          className="wf2-customerPageAction"
          onClick={() => navigate("/loyalty/dashboard")}
        >
          Loyalty Dashboard
        </button>
      </div>

      <div className="wf2-customerStats">
        <div className="wf2-customerStatCard">
          <span>Wallet balance</span>
          <strong>NPR {Number(wallet?.balance || 0).toLocaleString()}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Spendable now</span>
          <strong>NPR {Number(wallet?.spendable_balance || 0).toLocaleString()}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Total credited</span>
          <strong>NPR {Number(wallet?.total_credited || 0).toLocaleString()}</strong>
        </div>
      </div>

      <div className="wf2-customerStats">
        <div className="wf2-customerStatCard">
          <span>Total debited</span>
          <strong>NPR {Number(wallet?.total_debited || 0).toLocaleString()}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Pending referrals</span>
          <strong>{Number(referralSummary?.pending || 0).toLocaleString()}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Rewarded referrals</span>
          <strong>{Number(referralSummary?.rewarded || 0).toLocaleString()}</strong>
        </div>
      </div>

      <div className="wf2-customerTableWrap" style={{ marginBottom: 16 }}>
        <div style={{ padding: 16, display: "grid", gap: 10 }}>
          <div style={{ fontWeight: 700 }}>Your referral code</div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <input
              type="text"
              className="form-control"
              readOnly
              value={String(referral?.code || "")}
              style={{ maxWidth: 240 }}
            />
            <button
              type="button"
              className="wf2-customerPageAction"
              onClick={() => handleCopy(referral?.code, "Referral code")}
            >
              Copy Code
            </button>
            <button
              type="button"
              className="wf2-customerPageAction"
              onClick={() => handleCopy(referral?.link, "Referral link")}
            >
              Copy Link
            </button>
          </div>
          <div style={{ color: "rgba(190, 207, 236, 0.92)", fontSize: 13 }}>
            Referrer reward: NPR {Number(rewardPolicy?.referrer_reward_amount || 0).toLocaleString()} | 
            Referred reward: NPR {Number(rewardPolicy?.referred_reward_amount || 0).toLocaleString()} | 
            Credit expiry: {Number(rewardPolicy?.expiry_days || 90)} days | 
            Checkout cap: {Number(wallet?.cap_percent || 0).toLocaleString()}%
          </div>
          {receivedReferral ? (
            <div style={{ color: "rgba(190, 207, 236, 0.92)", fontSize: 13 }}>
              You joined using referral code {receivedReferral.referral_code} from {receivedReferral.referrer_name || "another user"}.
            </div>
          ) : null}
        </div>
      </div>

      {error ? <div className="wf2-customerError">{error}</div> : null}
      {notice ? <div className="wf2-customerSuccess">{notice}</div> : null}

      <div className="wf2-customerTableWrap" style={{ marginBottom: 16 }}>
        <table className="wf2-customerTable">
          <thead>
            <tr>
              <th>Referred User</th>
              <th>Status</th>
              <th>Booking Trigger</th>
              <th>Created</th>
              <th>Expires</th>
            </tr>
          </thead>
          <tbody>
            {sentReferrals.map((item) => (
              <tr key={item.id}>
                <td>{item.referred_user_name || item.referred_user_email || "-"}</td>
                <td>{toLabel(item.status)}</td>
                <td>{item.reward_trigger_booking_id ? `#${item.reward_trigger_booking_id}` : "-"}</td>
                <td>{formatDateTime(item.created_at)}</td>
                <td>{formatDateTime(item.expires_at)}</td>
              </tr>
            ))}
            {!loading && sentReferrals.length === 0 ? (
              <tr>
                <td colSpan="5">No referrals yet.</td>
              </tr>
            ) : null}
            {loading ? (
              <tr>
                <td colSpan="5">Loading referrals...</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="wf2-customerTableWrap">
        <table className="wf2-customerTable">
          <thead>
            <tr>
              <th>Type</th>
              <th>Reason</th>
              <th>Amount</th>
              <th>Status</th>
              <th>Remaining</th>
              <th>Created</th>
              <th>Expires</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx) => (
              <tr key={tx.id}>
                <td>{toLabel(tx.transaction_type)}</td>
                <td>{toLabel(tx.reason)}</td>
                <td>NPR {Number(tx.amount || 0).toLocaleString()}</td>
                <td>{toLabel(tx.status)}</td>
                <td>NPR {Number(tx.remaining_amount || 0).toLocaleString()}</td>
                <td>{formatDateTime(tx.created_at)}</td>
                <td>{formatDateTime(tx.expires_at)}</td>
              </tr>
            ))}
            {!loading && transactions.length === 0 ? (
              <tr>
                <td colSpan="7">No wallet transactions yet.</td>
              </tr>
            ) : null}
            {loading ? (
              <tr>
                <td colSpan="7">Loading wallet transactions...</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function toLabel(value) {
  const text = String(value || "").trim();
  if (!text) return "-";
  return text
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatDateTime(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}
