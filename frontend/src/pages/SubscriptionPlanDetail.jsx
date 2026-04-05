import React, { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  fetchSubscriptionPlanDetail,
  subscribeToPlan,
  upgradeSubscription,
} from "../lib/catalogApi";
import "../css/customerPages.css";

export default function SubscriptionPlanDetail() {
  const navigate = useNavigate();
  const { planId } = useParams();

  const [plan, setPlan] = useState(null);
  const [activeSubscription, setActiveSubscription] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [processing, setProcessing] = useState(false);

  const loadDetail = async (active = true) => {
    const id = Number(planId || 0);
    if (!id) {
      setError("Invalid plan id.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError("");
    try {
      const data = await fetchSubscriptionPlanDetail(id);
      if (!active) return;
      setPlan(data?.plan || null);
      setActiveSubscription(data?.active_subscription || null);
    } catch (err) {
      if (!active) return;
      setPlan(null);
      setActiveSubscription(null);
      setError(err.message || "Unable to load plan details.");
    } finally {
      if (active) setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    loadDetail(active);
    return () => {
      active = false;
    };
  }, [planId]);

  const handleAction = async () => {
    if (!plan?.id || processing) return;

    setProcessing(true);
    setError("");
    setNotice("");
    try {
      if (activeSubscription && Number(activeSubscription.plan_id) !== Number(plan.id)) {
        const response = await upgradeSubscription({
          plan_id: plan.id,
          payment_method: "ESEWA",
        });
        setNotice(response?.message || "Subscription upgraded.");
      } else if (!activeSubscription) {
        const response = await subscribeToPlan({
          plan_id: plan.id,
          payment_method: "ESEWA",
        });
        setNotice(response?.message || "Subscription activated.");
      } else {
        setNotice("You already have this plan active.");
      }
      await loadDetail(true);
    } catch (err) {
      setError(err.message || "Unable to process request.");
    } finally {
      setProcessing(false);
    }
  };

  return (
    <section className="wf2-customerPage">
      <div className="wf2-customerPageHead">
        <div>
          <h1>Plan Detail</h1>
          <p>Review all membership benefits and activation terms.</p>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button
            type="button"
            className="wf2-customerPageAction"
            onClick={() => navigate("/subscriptions/plans")}
          >
            Back to Plans
          </button>
          <button
            type="button"
            className="wf2-customerPageAction"
            onClick={() => navigate("/subscriptions/dashboard")}
          >
            My Membership
          </button>
        </div>
      </div>

      {error ? <div className="wf2-customerError">{error}</div> : null}
      {notice ? <div className="wf2-customerSuccess">{notice}</div> : null}

      {loading ? (
        <div className="wf2-customerTableWrap">
          <div style={{ padding: 16 }}>Loading plan details...</div>
        </div>
      ) : null}

      {!loading && !plan ? (
        <div className="wf2-customerTableWrap">
          <div style={{ padding: 16 }}>Plan not found.</div>
        </div>
      ) : null}

      {plan ? (
        <>
          <div className="wf2-customerStats">
            <div className="wf2-customerStatCard">
              <span>Plan Name</span>
              <strong>{plan.name}</strong>
            </div>
            <div className="wf2-customerStatCard">
              <span>Tier</span>
              <strong>{toLabel(plan.tier)}</strong>
            </div>
            <div className="wf2-customerStatCard">
              <span>Price</span>
              <strong>
                {plan.currency || "NPR"} {Number(plan.price || 0).toLocaleString()}
              </strong>
            </div>
          </div>

          <div className="wf2-customerStats">
            <div className="wf2-customerStatCard">
              <span>Duration</span>
              <strong>{Number(plan.duration_days || 0)} days</strong>
            </div>
            <div className="wf2-customerStatCard">
              <span>Free Tickets</span>
              <strong>{Number(plan.free_tickets_total || 0).toLocaleString()}</strong>
            </div>
            <div className="wf2-customerStatCard">
              <span>Max Discount</span>
              <strong>
                {Number(plan.max_discount_amount || 0) > 0
                  ? `${plan.currency || "NPR"} ${Number(plan.max_discount_amount || 0).toLocaleString()}`
                  : "No cap"}
              </strong>
            </div>
          </div>

          <div className="wf2-customerTableWrap" style={{ padding: 16 }}>
            <div style={{ display: "grid", gap: 10 }}>
              <div style={{ fontWeight: 700, fontSize: 18 }}>{plan.description || "No additional description."}</div>
              <div style={{ color: "rgba(190, 207, 236, 0.92)", fontSize: 14 }}>
                Discount type: {toLabel(plan.discount_type)} | Discount value: {Number(plan.discount_value || 0)}
              </div>
              <div style={{ color: "rgba(190, 207, 236, 0.92)", fontSize: 14 }}>
                Stackable with coupon: {plan.is_stackable_with_coupon ? "Yes" : "No"} | 
                Stackable with loyalty: {plan.is_stackable_with_loyalty ? "Yes" : "No"} | 
                Stackable with referral wallet: {plan.is_stackable_with_referral_wallet ? "Yes" : "No"}
              </div>
              <div style={{ color: "rgba(190, 207, 236, 0.92)", fontSize: 14 }}>
                Early access: {Number(plan.early_access_hours || 0)} hours | 
                Subscription-only access: {plan.subscription_only_access ? "Enabled" : "Disabled"}
              </div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <button
                  type="button"
                  className="wf2-customerPageAction"
                  disabled={processing}
                  onClick={handleAction}
                >
                  {processing
                    ? "Processing..."
                    : activeSubscription?.plan_id === plan.id
                      ? "Current Plan"
                      : activeSubscription
                        ? "Upgrade to this Plan"
                        : "Subscribe Now"}
                </button>
              </div>
            </div>
          </div>
        </>
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
