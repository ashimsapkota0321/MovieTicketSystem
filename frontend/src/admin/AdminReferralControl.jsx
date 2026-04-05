import { useEffect, useMemo, useState } from "react";
import AdminPageHeader from "./components/AdminPageHeader";
import {
  fetchAdminReferralControls,
  updateAdminReferralPolicy,
  updateAdminReferralStatus,
} from "../lib/catalogApi";

const FILTER_OPTIONS = ["", "PENDING", "REWARDED", "REJECTED", "REVERSED", "EXPIRED"];

export default function AdminReferralControl() {
  const [loading, setLoading] = useState(false);
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [statusFilter, setStatusFilter] = useState("");
  const [policy, setPolicy] = useState(null);
  const [summary, setSummary] = useState({});
  const [referrals, setReferrals] = useState([]);

  const pendingCount = useMemo(() => Number(summary?.pending || 0), [summary]);

  const loadData = async (requestedStatus = statusFilter) => {
    setLoading(true);
    setError("");
    try {
      const payload = await fetchAdminReferralControls(
        requestedStatus ? { status: requestedStatus } : {}
      );
      setPolicy(payload?.policy || null);
      setSummary(payload?.summary || {});
      setReferrals(Array.isArray(payload?.referrals) ? payload.referrals : []);
    } catch (err) {
      setError(err.message || "Unable to load referral controls.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSavePolicy = async () => {
    if (!policy || savingPolicy) return;

    setSavingPolicy(true);
    setError("");
    setNotice("");
    try {
      const payload = {
        referrer_reward_amount: Number(policy.referrer_reward_amount || 0),
        referred_reward_amount: Number(policy.referred_reward_amount || 0),
        reward_expiry_days: Number(policy.reward_expiry_days || 0),
        wallet_cap_percent: Number(policy.wallet_cap_percent || 0),
        max_signups_per_ip_per_day: Number(policy.max_signups_per_ip_per_day || 1),
        max_signups_per_device_per_day: Number(policy.max_signups_per_device_per_day || 1),
        auto_approve_rewards: Boolean(policy.auto_approve_rewards),
        is_active: Boolean(policy.is_active),
      };
      const updated = await updateAdminReferralPolicy(payload);
      setPolicy(updated || policy);
      setNotice("Referral policy updated.");
      await loadData();
    } catch (err) {
      setError(err.message || "Unable to update referral policy.");
    } finally {
      setSavingPolicy(false);
    }
  };

  const handleStatusAction = async (referral, action) => {
    if (!referral?.id) return;

    const payload = { action };
    if (action === "REJECT") {
      payload.rejection_reason = window.prompt("Enter rejection reason") || "Rejected by admin";
    }
    if (action === "REVERSE") {
      payload.reversal_reason = window.prompt("Enter reversal reason") || "Reversed by admin";
    }

    setError("");
    setNotice("");
    try {
      await updateAdminReferralStatus(referral.id, payload);
      setNotice(`Referral ${referral.id} updated to ${action}.`);
      await loadData();
    } catch (err) {
      setError(err.message || "Unable to update referral status.");
    }
  };

  return (
    <div className="d-flex flex-column gap-3">
      <AdminPageHeader
        title="Referral Governance"
        subtitle="Configure anti-abuse policy and moderate referral reward lifecycle."
      >
        <div className="d-flex align-items-center gap-2">
          <select
            className="form-select"
            value={statusFilter}
            onChange={async (event) => {
              const next = event.target.value;
              setStatusFilter(next);
              await loadData(next);
            }}
          >
            {FILTER_OPTIONS.map((option) => (
              <option key={option || "all"} value={option}>
                {option || "ALL STATUSES"}
              </option>
            ))}
          </select>
        </div>
      </AdminPageHeader>

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-3 mb-3">
          <StatusCard label="Pending" value={pendingCount} />
          <StatusCard label="Rewarded" value={Number(summary?.rewarded || 0)} />
          <StatusCard label="Rejected" value={Number(summary?.rejected || 0)} />
          <StatusCard label="Reversed" value={Number(summary?.reversed || 0)} />
          <StatusCard label="Total" value={Number(summary?.total || 0)} />
        </div>

        {error ? <div className="alert alert-danger">{error}</div> : null}
        {notice ? <div className="alert alert-success">{notice}</div> : null}
        {loading ? <div className="text-muted">Loading referral controls...</div> : null}

        {policy ? (
          <div className="row g-2">
            <NumberInput
              label="Referrer Reward"
              value={policy.referrer_reward_amount}
              step="0.01"
              onChange={(value) =>
                setPolicy((prev) => ({ ...prev, referrer_reward_amount: value }))
              }
            />
            <NumberInput
              label="Referred Reward"
              value={policy.referred_reward_amount}
              step="0.01"
              onChange={(value) =>
                setPolicy((prev) => ({ ...prev, referred_reward_amount: value }))
              }
            />
            <NumberInput
              label="Expiry Days"
              value={policy.reward_expiry_days}
              onChange={(value) => setPolicy((prev) => ({ ...prev, reward_expiry_days: value }))}
            />
            <NumberInput
              label="Wallet Cap (%)"
              value={policy.wallet_cap_percent}
              step="0.01"
              onChange={(value) => setPolicy((prev) => ({ ...prev, wallet_cap_percent: value }))}
            />
            <NumberInput
              label="Max Signups/IP/Day"
              value={policy.max_signups_per_ip_per_day}
              onChange={(value) =>
                setPolicy((prev) => ({ ...prev, max_signups_per_ip_per_day: value }))
              }
            />
            <NumberInput
              label="Max Signups/Device/Day"
              value={policy.max_signups_per_device_per_day}
              onChange={(value) =>
                setPolicy((prev) => ({ ...prev, max_signups_per_device_per_day: value }))
              }
            />

            <div className="col-md-6 d-flex gap-3 align-items-center">
              <label className="form-check mb-0">
                <input
                  className="form-check-input"
                  type="checkbox"
                  checked={Boolean(policy.auto_approve_rewards)}
                  onChange={(event) =>
                    setPolicy((prev) => ({
                      ...prev,
                      auto_approve_rewards: event.target.checked,
                    }))
                  }
                />
                <span className="ms-1">Auto approve rewards</span>
              </label>

              <label className="form-check mb-0">
                <input
                  className="form-check-input"
                  type="checkbox"
                  checked={Boolean(policy.is_active)}
                  onChange={(event) =>
                    setPolicy((prev) => ({ ...prev, is_active: event.target.checked }))
                  }
                />
                <span className="ms-1">Referral program active</span>
              </label>
            </div>

            <div className="col-12">
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleSavePolicy}
                disabled={savingPolicy}
              >
                {savingPolicy ? "Saving..." : "Save Referral Policy"}
              </button>
            </div>
          </div>
        ) : null}
      </section>

      <section className="admin-card">
        <h5 className="mb-3">Referral Queue</h5>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Code</th>
                <th>Referrer</th>
                <th>Referred User</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {referrals.map((item) => (
                <tr key={item.id}>
                  <td>{item.id}</td>
                  <td>{item.referral_code || "-"}</td>
                  <td>{item.referrer_name || item.referrer_id}</td>
                  <td>{item.referred_user_name || item.referred_user_email || item.referred_user_id}</td>
                  <td>{item.status}</td>
                  <td>{formatDate(item.created_at)}</td>
                  <td>
                    <div className="d-flex gap-2 flex-wrap">
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-light"
                        onClick={() => handleStatusAction(item, "APPROVE")}
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-light"
                        onClick={() => handleStatusAction(item, "REJECT")}
                      >
                        Reject
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-light"
                        onClick={() => handleStatusAction(item, "REVERSE")}
                      >
                        Reverse
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-light"
                        onClick={() => handleStatusAction(item, "PENDING")}
                      >
                        Set Pending
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && referrals.length === 0 ? (
                <tr>
                  <td colSpan="7">No referrals found.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function NumberInput({ label, value, onChange, step = "1" }) {
  return (
    <div className="col-md-3">
      <label className="form-label">{label}</label>
      <input
        className="form-control"
        type="number"
        min="0"
        step={step}
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function StatusCard({ label, value }) {
  return (
    <div className="border rounded px-3 py-2">
      <div className="text-muted small">{label}</div>
      <div className="fw-semibold">{value}</div>
    </div>
  );
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString();
}
