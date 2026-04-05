import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  fetchSubscriptionPlans,
  subscribeToPlan,
  upgradeSubscription,
} from "../lib/catalogApi";
import "../css/customerPages.css";

const TIER_OPTIONS = ["ALL", "SILVER", "GOLD", "PLATINUM"];

export default function SubscriptionPlans() {
  const navigate = useNavigate();
  const [plans, setPlans] = useState([]);
  const [activeSubscription, setActiveSubscription] = useState(null);
  const [selectedTier, setSelectedTier] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyPlanId, setBusyPlanId] = useState(null);

  const loadPlans = async (active = true) => {
    setLoading(true);
    setError("");
    try {
      const params = {};
      if (selectedTier && selectedTier !== "ALL") {
        params.tier = selectedTier;
      }
      const data = await fetchSubscriptionPlans(params);
      if (!active) return;
      setPlans(Array.isArray(data?.plans) ? data.plans : []);
      setActiveSubscription(data?.active_subscription || null);
    } catch (err) {
      if (!active) return;
      setPlans([]);
      setActiveSubscription(null);
      setError(err.message || "Unable to load subscription plans.");
    } finally {
      if (active) setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    loadPlans(active);
    return () => {
      active = false;
    };
  }, [selectedTier]);

  const groupedPlans = useMemo(() => {
    const map = new Map();
    plans.forEach((plan) => {
      const key = plan?.vendor_name || "Global Plans";
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(plan);
    });
    return Array.from(map.entries());
  }, [plans]);

  const handleSubscribe = async (plan) => {
    const planId = Number(plan?.id || 0);
    if (!planId || busyPlanId === planId) return;

    setBusyPlanId(planId);
    setError("");
    setNotice("");

    try {
      const hasActive = Boolean(activeSubscription?.id);
      if (hasActive && Number(activeSubscription?.plan_id) !== planId) {
        const response = await upgradeSubscription({
          plan_id: planId,
          payment_method: "ESEWA",
        });
        setNotice(response?.message || "Subscription upgraded successfully.");
      } else if (hasActive) {
        setNotice("You already have this plan active.");
      } else {
        const response = await subscribeToPlan({
          plan_id: planId,
          payment_method: "ESEWA",
        });
        setNotice(response?.message || "Subscription activated successfully.");
      }
      await loadPlans(true);
    } catch (err) {
      setError(err.message || "Unable to process subscription action.");
    } finally {
      setBusyPlanId(null);
    }
  };

  return (
    <section className="wf2-customerPage">
      <div className="wf2-customerPageHead">
        <div>
          <h1>Membership Plans</h1>
          <p>Unlock discounts, free tickets, and priority perks across cinemas.</p>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button
            type="button"
            className="wf2-customerPageAction"
            onClick={() => navigate("/subscriptions/dashboard")}
          >
            My Membership
          </button>
          <button
            type="button"
            className="wf2-customerPageAction"
            onClick={() => navigate("/loyalty/dashboard")}
          >
            Loyalty Dashboard
          </button>
        </div>
      </div>

      <div className="wf2-customerStats">
        <div className="wf2-customerStatCard">
          <span>Active plan</span>
          <strong>{activeSubscription?.plan_name || "None"}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Tier</span>
          <strong>{toLabel(activeSubscription?.tier || "-")}</strong>
        </div>
        <div className="wf2-customerStatCard">
          <span>Free tickets left</span>
          <strong>{Number(activeSubscription?.remaining_free_tickets || 0).toLocaleString()}</strong>
        </div>
      </div>

      <div className="wf2-customerTableWrap" style={{ marginBottom: 16 }}>
        <div style={{ padding: 16, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div style={{ fontWeight: 700 }}>Filter Tier</div>
          <select
            className="form-select"
            value={selectedTier}
            onChange={(event) => setSelectedTier(event.target.value)}
            style={{ maxWidth: 220 }}
          >
            {TIER_OPTIONS.map((item) => (
              <option key={item} value={item}>
                {toLabel(item)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {error ? <div className="wf2-customerError">{error}</div> : null}
      {notice ? <div className="wf2-customerSuccess">{notice}</div> : null}

      {groupedPlans.map(([group, items]) => (
        <div className="wf2-customerTableWrap" key={group} style={{ marginBottom: 16 }}>
          <div style={{ padding: 16, fontWeight: 700 }}>{group}</div>
          <table className="wf2-customerTable">
            <thead>
              <tr>
                <th>Plan</th>
                <th>Tier</th>
                <th>Price</th>
                <th>Benefits</th>
                <th>Validity</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {items.map((plan) => (
                <tr key={plan.id}>
                  <td>
                    <div style={{ fontWeight: 700 }}>{plan.name}</div>
                    <div className="text-muted small">{plan.description || "-"}</div>
                  </td>
                  <td>{toLabel(plan.tier)}</td>
                  <td>
                    {plan.currency || "NPR"} {Number(plan.price || 0).toLocaleString()}
                  </td>
                  <td>
                    {formatBenefits(plan)}
                  </td>
                  <td>{Number(plan.duration_days || 0)} days</td>
                  <td>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button
                        type="button"
                        className="wf2-customerPageAction"
                        onClick={() => navigate(`/subscriptions/plans/${plan.id}`)}
                      >
                        Details
                      </button>
                      <button
                        type="button"
                        className="wf2-customerPageAction"
                        disabled={busyPlanId === plan.id}
                        onClick={() => handleSubscribe(plan)}
                      >
                        {busyPlanId === plan.id
                          ? "Processing..."
                          : activeSubscription?.plan_id === plan.id
                            ? "Current"
                            : activeSubscription
                              ? "Upgrade"
                              : "Subscribe"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && items.length === 0 ? (
                <tr>
                  <td colSpan="6">No plans found for this group.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      ))}

      {!loading && plans.length === 0 ? (
        <div className="wf2-customerTableWrap">
          <div style={{ padding: 16 }}>No membership plans are available right now.</div>
        </div>
      ) : null}
      {loading ? (
        <div className="wf2-customerTableWrap">
          <div style={{ padding: 16 }}>Loading membership plans...</div>
        </div>
      ) : null}
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

function formatBenefits(plan) {
  const parts = [];
  if (String(plan?.discount_type || "") !== "NONE") {
    if (String(plan?.discount_type || "") === "PERCENTAGE") {
      parts.push(`${Number(plan?.discount_value || 0)}% off`);
    } else {
      parts.push(`${plan?.currency || "NPR"} ${Number(plan?.discount_value || 0)} off`);
    }
  }
  if (Number(plan?.free_tickets_total || 0) > 0) {
    parts.push(`${Number(plan?.free_tickets_total || 0)} free tickets`);
  }
  if (Number(plan?.max_discount_amount || 0) > 0) {
    parts.push(`Max ${plan?.currency || "NPR"} ${Number(plan?.max_discount_amount || 0)}`);
  }
  if (!parts.length) return "No discount benefits";
  return parts.join(" | ");
}
