import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  cancelSubscription,
  fetchSubscriptionDashboard,
} from "../lib/catalogApi";
import "../css/customerPages.css";

export default function SubscriptionDashboard() {
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [cancelling, setCancelling] = useState(false);

  const loadDashboard = async (active = true) => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchSubscriptionDashboard();
      if (!active) return;
      setDashboard(data || null);
    } catch (err) {
      if (!active) return;
      setDashboard(null);
      setError(err.message || "Unable to load subscription dashboard.");
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

  const activeSubscription = dashboard?.active_subscription || null;
  const subscriptions = Array.isArray(dashboard?.subscriptions) ? dashboard.subscriptions : [];
  const transactions = Array.isArray(dashboard?.transactions) ? dashboard.transactions : [];

  const handleCancel = async (immediate) => {
    if (!activeSubscription?.id || cancelling) return;

    const confirmMessage = immediate
      ? "Cancel now and process prorated refund if available?"
      : "Schedule cancellation at period end?";
    if (!window.confirm(confirmMessage)) return;

    setCancelling(true);
    setError("");
    setNotice("");
    try {
      const response = await cancelSubscription({ immediate });
      setNotice(response?.message || "Subscription update successful.");
      await loadDashboard(true);
    } catch (err) {
      setError(err.message || "Unable to cancel subscription.");
    } finally {
      setCancelling(false);
    }
  };

  return (
    <section className="wf2-customerPage">
      <div className="wf2-customerPageHead">
        <div>
          <h1>My Membership</h1>
          <p>Monitor your active plan, benefits usage, and subscription transactions.</p>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button
            type="button"
            className="wf2-customerPageAction"
            onClick={() => navigate("/subscriptions/plans")}
          >
            Browse Plans
          </button>
          <button
            type="button"
            className="wf2-customerPageAction"
            onClick={() => navigate("/bookings/history")}
          >
            Booking History
          </button>
        </div>
      </div>

      {error ? <div className="wf2-customerError">{error}</div> : null}
      {notice ? <div className="wf2-customerSuccess">{notice}</div> : null}

      <div className="wf2-customerStats">
        <div className="wf2-customerStatCard">
          <span>Current plan</span>
          <strong>{activeSubscription?.plan_name || "No active plan"}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Tier</span>
          <strong>{toLabel(activeSubscription?.tier || "-")}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Days remaining</span>
          <strong>{Number(activeSubscription?.days_remaining || 0).toLocaleString()}</strong>
        </div>
      </div>

      <div className="wf2-customerStats">
        <div className="wf2-customerStatCard">
          <span>Free tickets remaining</span>
          <strong>{Number(activeSubscription?.remaining_free_tickets || 0).toLocaleString()}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Free tickets used</span>
          <strong>{Number(activeSubscription?.used_free_tickets || 0).toLocaleString()}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Total discount used</span>
          <strong>
            {activeSubscription?.plan?.currency || "NPR"} {Number(activeSubscription?.total_discount_used || 0).toLocaleString()}
          </strong>
        </div>
      </div>

      {activeSubscription ? (
        <div className="wf2-customerTableWrap" style={{ marginBottom: 16 }}>
          <div style={{ padding: 16, display: "flex", gap: 10, flexWrap: "wrap" }}>
            <button
              type="button"
              className="wf2-customerPageAction"
              disabled={cancelling || Boolean(activeSubscription?.cancel_at_period_end)}
              onClick={() => handleCancel(false)}
            >
              {activeSubscription?.cancel_at_period_end ? "Cancellation Scheduled" : "Cancel at Period End"}
            </button>
            <button
              type="button"
              className="wf2-customerPageAction"
              disabled={cancelling}
              onClick={() => handleCancel(true)}
            >
              {cancelling ? "Processing..." : "Cancel Immediately"}
            </button>
          </div>
        </div>
      ) : null}

      <div className="wf2-customerTableWrap" style={{ marginBottom: 16 }}>
        <table className="wf2-customerTable">
          <thead>
            <tr>
              <th>Plan</th>
              <th>Status</th>
              <th>Tier</th>
              <th>Start</th>
              <th>End</th>
              <th>Free Tickets</th>
            </tr>
          </thead>
          <tbody>
            {subscriptions.map((item) => (
              <tr key={item.id}>
                <td>{item.plan_name || `Plan #${item.plan_id}`}</td>
                <td>{toLabel(item.status)}</td>
                <td>{toLabel(item.tier)}</td>
                <td>{formatDateTime(item.start_at)}</td>
                <td>{formatDateTime(item.end_at)}</td>
                <td>
                  {Number(item.remaining_free_tickets || 0)} / {Number((item.used_free_tickets || 0) + (item.remaining_free_tickets || 0))}
                </td>
              </tr>
            ))}
            {!loading && subscriptions.length === 0 ? (
              <tr>
                <td colSpan="6">No subscription history available.</td>
              </tr>
            ) : null}
            {loading ? (
              <tr>
                <td colSpan="6">Loading subscription history...</td>
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
              <th>Status</th>
              <th>Amount</th>
              <th>Discount</th>
              <th>Free Tickets</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx) => (
              <tr key={tx.id}>
                <td>{toLabel(tx.transaction_type)}</td>
                <td>{toLabel(tx.status)}</td>
                <td>{tx.currency || "NPR"} {Number(tx.amount || 0).toLocaleString()}</td>
                <td>{tx.currency || "NPR"} {Number(tx.discount_amount || 0).toLocaleString()}</td>
                <td>{Number(tx.free_tickets_used || 0).toLocaleString()}</td>
                <td>{formatDateTime(tx.created_at)}</td>
              </tr>
            ))}
            {!loading && transactions.length === 0 ? (
              <tr>
                <td colSpan="6">No subscription transactions yet.</td>
              </tr>
            ) : null}
            {loading ? (
              <tr>
                <td colSpan="6">Loading subscription transactions...</td>
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
