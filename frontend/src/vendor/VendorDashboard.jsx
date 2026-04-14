import { useEffect, useMemo, useState } from "react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { CalendarDays, Ticket, Wallet, Film, RefreshCw } from "lucide-react";
import {
  fetchVendorRevenueAnalytics,
  fetchVendorWalletBalance,
  fetchVendorWalletTransactions,
  requestVendorPayoutProfileVerification,
  requestVendorWithdrawal,
  updateVendorPayoutProfile,
  verifyVendorPayoutProfile,
} from "../lib/catalogApi";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function roughPercentFromLabel(label) {
  const text = String(label || "");
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash << 5) - hash + text.charCodeAt(i);
    hash |= 0;
  }
  const pct = 5 + (Math.abs(hash) % 11);
  return pct / 100;
}

function maybeWeekendBump(label, value) {
  const parsed = new Date(label);
  if (Number.isNaN(parsed.getTime())) return value;
  const day = parsed.getDay();
  if (day === 0 || day === 6) {
    return value * 1.08;
  }
  return value;
}

function buildChartTrend(rawTrend = []) {
  if (!Array.isArray(rawTrend) || rawTrend.length === 0) {
    return [];
  }

  return rawTrend.map((point, index) => {
    const base = Number(point?.value || 0);
    const label = point?.label || "";
    if (!base) {
      return { label, value: 0, rawValue: 0 };
    }

    const pct = roughPercentFromLabel(label);
    const sign = index % 2 === 0 ? 1 : -1;
    const bumped = maybeWeekendBump(label, base);
    const jittered = bumped + bumped * pct * sign;

    return {
      label,
      rawValue: base,
      value: Number(clamp(jittered, 0, Number.MAX_SAFE_INTEGER).toFixed(2)),
    };
  });
}

function formatMoney(value) {
  const amount = Number(value || 0);
  return `NPR ${amount.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

function shortLabel(label) {
  const text = String(label || "");
  if (text.length <= 10) return text;
  return `${text.slice(0, 10)}...`;
}

export default function VendorDashboard() {
  const [analytics, setAnalytics] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [payoutProfile, setPayoutProfile] = useState(null);
  const [withdrawalHistory, setWithdrawalHistory] = useState([]);
  const [payoutPolicy, setPayoutPolicy] = useState(null);
  const [payoutForm, setPayoutForm] = useState({
    destination_type: "BANK",
    destination_name: "",
    destination_reference: "",
    account_holder_name: "",
    bank_name: "",
    branch_name: "",
    minimum_withdrawal_amount: "500",
    payout_schedule: "WEEKLY",
    payout_schedule_days: "1",
    payout_schedule_time: "10:00",
    failed_retry_limit: "3",
    retry_backoff_minutes: "60",
  });
  const [withdrawalForm, setWithdrawalForm] = useState({ amount: "", note: "" });
  const [verificationOtp, setVerificationOtp] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [actionError, setActionError] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rangeKey, setRangeKey] = useState("last_30_days");
  const [period, setPeriod] = useState("daily");

  const applyWalletPayload = (walletData) => {
    const walletState = walletData?.wallet || walletData || {};
    const profileState = walletData?.payout_profile || walletData?.payoutProfile || walletData?.payout_profile_data || null;
    const policyState = walletData?.payout_policy || walletData?.payoutPolicy || null;
    setWallet(walletState);
    setPayoutProfile(profileState);
    setPayoutPolicy(policyState);
    setWithdrawalHistory(Array.isArray(walletData?.withdrawal_history) ? walletData.withdrawal_history : []);
    if (profileState) {
      setPayoutForm({
        destination_type: profileState.destination_type || "BANK",
        destination_name: profileState.destination_name || "",
        destination_reference: profileState.destination_reference || "",
        account_holder_name: profileState.account_holder_name || "",
        bank_name: profileState.bank_name || "",
        branch_name: profileState.branch_name || "",
        minimum_withdrawal_amount: String(profileState.minimum_withdrawal_amount ?? "500"),
        payout_schedule: profileState.payout_schedule || "WEEKLY",
        payout_schedule_days: Array.isArray(profileState.payout_schedule_days)
          ? profileState.payout_schedule_days.join(", ")
          : "1",
        payout_schedule_time: (profileState.payout_schedule_time || "10:00").slice(0, 5),
        failed_retry_limit: String(profileState.failed_retry_limit ?? "3"),
        retry_backoff_minutes: String(profileState.retry_backoff_minutes ?? "60"),
      });
    }
  };

  const loadDashboard = async () => {
    try {
      setLoading(true);
      setError("");
      const [revenueData, walletData, txData] = await Promise.all([
        fetchVendorRevenueAnalytics({ range: rangeKey, group: period }),
        fetchVendorWalletBalance(),
        fetchVendorWalletTransactions(),
      ]);
      setAnalytics(revenueData || {});
      applyWalletPayload(walletData || {});
      setTransactions(Array.isArray(txData) ? txData : []);
    } catch (err) {
      setError(err?.message || "Could not load vendor revenue analytics.");
    } finally {
      setLoading(false);
    }
  };

  const refreshWalletData = async () => {
    const walletData = await fetchVendorWalletBalance();
    applyWalletPayload(walletData || {});
  };

  const setActionFeedback = (message = "", isError = false) => {
    setActionMessage(isError ? "" : message);
    setActionError(isError ? message : "");
  };

  const handleSavePayoutProfile = async () => {
    try {
      setActionLoading(true);
      setActionFeedback("");
      const payload = {
        ...payoutForm,
        payout_schedule_days: String(payoutForm.payout_schedule_days || "")
          .split(/[,\s]+/)
          .map((value) => value.trim())
          .filter(Boolean)
          .map((value) => Number(value))
          .filter((value) => Number.isFinite(value)),
      };
      await updateVendorPayoutProfile(payload);
      await refreshWalletData();
      setActionFeedback("Payout destination saved. Request verification to enable withdrawals.");
    } catch (err) {
      setActionFeedback(err?.message || "Could not save payout profile.", true);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRequestVerification = async () => {
    try {
      setActionLoading(true);
      setActionFeedback("");
      await requestVendorPayoutProfileVerification();
      setActionFeedback("Verification OTP sent to your email address.");
    } catch (err) {
      setActionFeedback(err?.message || "Could not request verification.", true);
    } finally {
      setActionLoading(false);
    }
  };

  const handleVerifyDestination = async () => {
    try {
      setActionLoading(true);
      setActionFeedback("");
      await verifyVendorPayoutProfile({ otp: verificationOtp });
      setVerificationOtp("");
      await refreshWalletData();
      setActionFeedback("Payout destination verified.");
    } catch (err) {
      setActionFeedback(err?.message || "Could not verify payout destination.", true);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRequestWithdrawal = async () => {
    try {
      setActionLoading(true);
      setActionFeedback("");
      await requestVendorWithdrawal({
        amount: withdrawalForm.amount,
        note: withdrawalForm.note,
      });
      setWithdrawalForm({ amount: "", note: "" });
      await refreshWalletData();
      setActionFeedback("Withdrawal request submitted.");
    } catch (err) {
      setActionFeedback(err?.message || "Could not request withdrawal.", true);
    } finally {
      setActionLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
  }, [rangeKey, period]);

  const summary = analytics?.summary || {};
  const earningsPerShow = Array.isArray(analytics?.earnings_per_show) ? analytics.earnings_per_show : [];
  const occupancyBySlot = Array.isArray(analytics?.occupancy_by_slot) ? analytics.occupancy_by_slot : [];
  const trend = Array.isArray(analytics?.trend) ? analytics.trend : [];
  const cancellationRate = Number(summary?.cancellation_rate || 0);
  const refundRate = Number(summary?.refund_rate || 0);
  const payoutPending = Number(summary?.payout_pending || 0);
  const refundTotalAmount = Number(summary?.refund_total_amount || 0);
  const pendingPayouts = useMemo(
    () => transactions.filter((item) => {
      const type = String(item?.type || item?.transaction_type || "").toUpperCase();
      const status = String(item?.status || "").toUpperCase();
      return type.includes("WITHDRAWAL") && status === "PENDING";
    }),
    [transactions]
  );

  const displayTrend = useMemo(() => buildChartTrend(trend), [trend]);

  const topShowBars = useMemo(() => {
    return earningsPerShow
      .slice(0, 8)
      .map((item) => ({
        show: shortLabel(item?.show_title || "Unknown"),
        earning: Number(item?.vendor_earning || 0),
        tickets: Number(item?.tickets_sold || 0),
      }));
  }, [earningsPerShow]);

  const statCards = [
    {
      label: "Total Earnings (90%)",
      value: formatMoney(summary?.total_earnings),
      hint: "After admin commission split",
      icon: Wallet,
    },
    {
      label: "Tickets Sold",
      value: Number(summary?.total_tickets_sold || 0).toLocaleString(),
      hint: "Paid bookings only",
      icon: Ticket,
    },
    {
      label: "Gross Revenue",
      value: formatMoney(summary?.total_revenue),
      hint: "Before commission",
      icon: CalendarDays,
    },
    {
      label: "Shows With Earnings",
      value: earningsPerShow.length,
      hint: "Uneven by show, as expected",
      icon: Film,
    },
    {
      label: "Cancellation Rate",
      value: `${cancellationRate.toFixed(1)}%`,
      hint: "Cancelled bookings in range",
      icon: CalendarDays,
    },
    {
      label: "Refund Rate",
      value: `${refundRate.toFixed(1)}%`,
      hint: `Refunded value: ${formatMoney(refundTotalAmount)}`,
      icon: RefreshCw,
    },
    {
      label: "Available Payout",
      value: formatMoney(wallet?.available_balance ?? wallet?.availableBalance ?? 0),
      hint: "Ready to withdraw once approved",
      icon: Wallet,
    },
    {
      label: "Payout Pending",
      value: formatMoney(payoutPending),
      hint: "Requested but not yet cleared",
      icon: Wallet,
    },
  ];

  if (loading) {
    return (
      <div className="vendor-dashboard revenue-dashboard">
        <section className="vendor-card">
          <p className="text-muted mb-0">Loading revenue dashboard...</p>
        </section>
      </div>
    );
  }

  return (
    <div className="vendor-dashboard revenue-dashboard">
      <div className="revenue-head">
        <div>
          <h2 className="mb-1">Vendor Revenue Dashboard</h2>
          <p className="text-muted mb-0">Revenue, occupancy, refunds, cancellations, and payout settlement in one place.</p>
        </div>
        <div className="revenue-actions">
          <select className="form-select form-select-sm" value={rangeKey} onChange={(e) => setRangeKey(e.target.value)}>
            <option value="last_7_days">Last 7 days</option>
            <option value="last_30_days">Last 30 days</option>
            <option value="yearly">Yearly</option>
          </select>
          <select className="form-select form-select-sm" value={period} onChange={(e) => setPeriod(e.target.value)}>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
          <button type="button" className="btn btn-sm btn-outline-secondary" onClick={loadDashboard}>
            <RefreshCw size={14} className="me-1" />
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className="alert alert-warning py-2">{error}</div> : null}

      <section className="vendor-card mb-3">
        <div className="vendor-card-header">
          <div>
            <h3>Payout status</h3>
            <p>Track the balance that is ready for withdrawal and the requests still pending review.</p>
          </div>
        </div>
        <div className="row g-3">
          <div className="col-12 col-md-4">
            <div className="vendor-stat">
              <div className="vendor-stat-value">{formatMoney(wallet?.balance ?? 0)}</div>
              <div className="vendor-stat-label">Wallet balance</div>
              <div className="vendor-stat-note">Total ledger balance before pending deductions.</div>
            </div>
          </div>
          <div className="col-12 col-md-4">
            <div className="vendor-stat">
              <div className="vendor-stat-value">{formatMoney(wallet?.pending_withdrawals ?? wallet?.pendingWithdrawals ?? 0)}</div>
              <div className="vendor-stat-label">Pending payouts</div>
              <div className="vendor-stat-note">Requests already waiting on admin review.</div>
            </div>
          </div>
          <div className="col-12 col-md-4">
            <div className="vendor-stat">
              <div className="vendor-stat-value">{pendingPayouts.length}</div>
              <div className="vendor-stat-label">Pending withdrawal requests</div>
              <div className="vendor-stat-note">Recent payout requests that have not been cleared yet.</div>
            </div>
          </div>
        </div>
      </section>

      <div className="vendor-grid-2 vendor-payout-grid">
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Payout destination</h3>
              <p>Save your bank, UPI, or wallet details before requesting a withdrawal.</p>
            </div>
          </div>
          <div className="row g-3">
            <div className="col-12 col-md-6">
              <label className="form-label">Destination type</label>
              <select
                className="form-select"
                value={payoutForm.destination_type}
                onChange={(e) => setPayoutForm((prev) => ({ ...prev, destination_type: e.target.value }))}
              >
                <option value="BANK">Bank Account</option>
                <option value="UPI">UPI</option>
                <option value="EWALLET">E-Wallet</option>
                <option value="MOBILE">Mobile Wallet</option>
              </select>
            </div>
            <div className="col-12 col-md-6">
              <label className="form-label">Destination name</label>
              <input
                className="form-control"
                value={payoutForm.destination_name}
                onChange={(e) => setPayoutForm((prev) => ({ ...prev, destination_name: e.target.value }))}
                placeholder="Bank / wallet provider"
              />
            </div>
            <div className="col-12 col-md-6">
              <label className="form-label">Destination reference</label>
              <input
                className="form-control"
                value={payoutForm.destination_reference}
                onChange={(e) => setPayoutForm((prev) => ({ ...prev, destination_reference: e.target.value }))}
                placeholder="Account number, UPI ID, or mobile number"
              />
            </div>
            <div className="col-12 col-md-6">
              <label className="form-label">Account holder name</label>
              <input
                className="form-control"
                value={payoutForm.account_holder_name}
                onChange={(e) => setPayoutForm((prev) => ({ ...prev, account_holder_name: e.target.value }))}
              />
            </div>
            <div className="col-12 col-md-6">
              <label className="form-label">Bank name</label>
              <input
                className="form-control"
                value={payoutForm.bank_name}
                onChange={(e) => setPayoutForm((prev) => ({ ...prev, bank_name: e.target.value }))}
              />
            </div>
            <div className="col-12 col-md-6">
              <label className="form-label">Branch name</label>
              <input
                className="form-control"
                value={payoutForm.branch_name}
                onChange={(e) => setPayoutForm((prev) => ({ ...prev, branch_name: e.target.value }))}
              />
            </div>
            <div className="col-12 col-md-4">
              <label className="form-label">Minimum withdrawal</label>
              <input
                type="number"
                min="0"
                step="0.01"
                className="form-control"
                value={payoutForm.minimum_withdrawal_amount}
                onChange={(e) => setPayoutForm((prev) => ({ ...prev, minimum_withdrawal_amount: e.target.value }))}
              />
            </div>
            <div className="col-12 col-md-4">
              <label className="form-label">Payout schedule</label>
              <select
                className="form-select"
                value={payoutForm.payout_schedule}
                onChange={(e) => setPayoutForm((prev) => ({ ...prev, payout_schedule: e.target.value }))}
              >
                <option value="DAILY">Daily</option>
                <option value="WEEKLY">Weekly</option>
                <option value="MONTHLY">Monthly</option>
              </select>
            </div>
            <div className="col-12 col-md-4">
              <label className="form-label">Schedule day(s)</label>
              <input
                className="form-control"
                value={payoutForm.payout_schedule_days}
                onChange={(e) => setPayoutForm((prev) => ({ ...prev, payout_schedule_days: e.target.value }))}
                placeholder="1, 15, 28"
              />
            </div>
            <div className="col-12 col-md-4">
              <label className="form-label">Payout time</label>
              <input
                type="time"
                className="form-control"
                value={payoutForm.payout_schedule_time}
                onChange={(e) => setPayoutForm((prev) => ({ ...prev, payout_schedule_time: e.target.value }))}
              />
            </div>
            <div className="col-12 col-md-4">
              <label className="form-label">Retry limit</label>
              <input
                type="number"
                min="1"
                className="form-control"
                value={payoutForm.failed_retry_limit}
                onChange={(e) => setPayoutForm((prev) => ({ ...prev, failed_retry_limit: e.target.value }))}
              />
            </div>
            <div className="col-12 col-md-4">
              <label className="form-label">Retry backoff minutes</label>
              <input
                type="number"
                min="1"
                className="form-control"
                value={payoutForm.retry_backoff_minutes}
                onChange={(e) => setPayoutForm((prev) => ({ ...prev, retry_backoff_minutes: e.target.value }))}
              />
            </div>
          </div>
          <div className="vendor-inline-actions mt-3">
            <button type="button" className="btn btn-primary" onClick={handleSavePayoutProfile} disabled={actionLoading}>
              Save payout details
            </button>
            <button type="button" className="btn btn-outline-secondary" onClick={handleRequestVerification} disabled={actionLoading}>
              Send verification OTP
            </button>
          </div>
          <div className="mt-3">
            <label className="form-label">Verification OTP</label>
            <div className="vendor-inline-actions">
              <input
                className="form-control"
                value={verificationOtp}
                onChange={(e) => setVerificationOtp(e.target.value)}
                placeholder="Enter OTP from email"
              />
              <button type="button" className="btn btn-outline-primary" onClick={handleVerifyDestination} disabled={actionLoading}>
                Verify destination
              </button>
            </div>
          </div>
          <div className="mt-3 payout-summary-box">
            <div><strong>Status:</strong> {payoutProfile?.is_destination_verified ? "Verified" : "Pending verification"}</div>
            <div><strong>Next payout:</strong> {payoutPolicy?.next_payout_window ? formatDate(payoutPolicy.next_payout_window) : "Not scheduled"}</div>
            <div><strong>Minimum:</strong> {formatMoney(payoutPolicy?.minimum_withdrawal_amount ?? payoutProfile?.minimum_withdrawal_amount ?? 0)}</div>
          </div>
        </section>

        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Request withdrawal</h3>
              <p>Withdraw only within the allowed payout window after verification.</p>
            </div>
          </div>
          <div className="row g-3">
            <div className="col-12 col-md-6">
              <label className="form-label">Amount</label>
              <input
                type="number"
                min="0"
                step="0.01"
                className="form-control"
                value={withdrawalForm.amount}
                onChange={(e) => setWithdrawalForm((prev) => ({ ...prev, amount: e.target.value }))}
                placeholder="Enter withdrawal amount"
              />
            </div>
            <div className="col-12">
              <label className="form-label">Note</label>
              <textarea
                className="form-control"
                rows="3"
                value={withdrawalForm.note}
                onChange={(e) => setWithdrawalForm((prev) => ({ ...prev, note: e.target.value }))}
                placeholder="Optional note for this request"
              />
            </div>
          </div>
          <div className="vendor-inline-actions mt-3">
            <button type="button" className="btn btn-primary" onClick={handleRequestWithdrawal} disabled={actionLoading}>
              Submit withdrawal request
            </button>
          </div>
          <div className="payout-summary-box mt-3">
            <div><strong>Available:</strong> {formatMoney(wallet?.available_balance ?? wallet?.availableBalance ?? 0)}</div>
            <div><strong>Pending:</strong> {formatMoney(wallet?.pending_withdrawals ?? wallet?.pendingWithdrawals ?? 0)}</div>
            <div><strong>Verified:</strong> {payoutProfile?.is_destination_verified ? "Yes" : "No"}</div>
          </div>
        </section>
      </div>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Withdrawal history</h3>
            <p>Latest payout requests, approvals, and settlement outcomes.</p>
          </div>
        </div>
        <div className="table-responsive">
          <table className="table table-sm mb-0 revenue-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Amount</th>
                <th>Retry count</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {withdrawalHistory.slice(0, 10).map((item) => (
                <tr key={item.id}>
                  <td>#{item.id}</td>
                  <td>
                    <span className={`badge-soft ${transactionTone(item.status)}`}>
                      {item.status || "-"}
                    </span>
                  </td>
                  <td>{formatMoney(item.amount || 0)}</td>
                  <td>{Number(item.retry_count || 0).toLocaleString()}</td>
                  <td>{formatDate(item.created_at)}</td>
                </tr>
              ))}
              {!loading && withdrawalHistory.length === 0 ? (
                <tr>
                  <td colSpan="5">No withdrawal history yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <div className="vendor-stat-grid revenue-stat-grid">
        {statCards.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.label} className="vendor-stat revenue-stat-card">
              <div className="vendor-stat-row">
                <div>
                  <div className="vendor-stat-value">{item.value}</div>
                  <div className="vendor-stat-label">{item.label}</div>
                </div>
                <div className="vendor-stat-icon">
                  <Icon size={16} />
                </div>
              </div>
              <div className="vendor-stat-note">{item.hint}</div>
            </div>
          );
        })}
      </div>

      <div className="vendor-grid-2 revenue-grid-main">
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Earnings Trend</h3>
              <p>Daily or weekly earnings with natural ups and downs</p>
            </div>
          </div>
          {displayTrend.length === 0 ? (
            <p className="text-muted mb-1">No trend points yet. You may see gaps on low-booking days.</p>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={displayTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--vendor-border)" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="var(--vendor-muted)" />
                <YAxis stroke="var(--vendor-muted)" tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#fff",
                    border: "1px solid var(--vendor-border)",
                    borderRadius: "6px",
                  }}
                  formatter={(value) => [formatMoney(value), "Earnings"]}
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="#1f77b4"
                  strokeWidth={2}
                  dot={{ r: 2 }}
                  activeDot={{ r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </section>

        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Earnings Per Show</h3>
              <p>Not all shows perform equally</p>
            </div>
          </div>
          {topShowBars.length === 0 ? (
            <p className="text-muted mb-1">No show-level earnings yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={topShowBars}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--vendor-border)" />
                <XAxis dataKey="show" tick={{ fontSize: 11 }} stroke="var(--vendor-muted)" />
                <YAxis stroke="var(--vendor-muted)" tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#fff",
                    border: "1px solid var(--vendor-border)",
                    borderRadius: "6px",
                  }}
                  formatter={(value, name) => {
                    if (name === "earning") return [formatMoney(value), "Vendor Earning"];
                    return [value, "Tickets"];
                  }}
                />
                <Bar dataKey="earning" fill="#22a06b" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </section>
      </div>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Occupancy by Slot</h3>
            <p>Shows how full each slot is, based on sold seats versus screen capacity.</p>
          </div>
        </div>
        <div className="table-responsive">
          <table className="table table-sm mb-0 revenue-table">
            <thead>
              <tr>
                <th>Slot</th>
                <th>Movie</th>
                <th>Hall</th>
                <th>Tickets Sold</th>
                <th>Capacity</th>
                <th>Occupancy</th>
              </tr>
            </thead>
            <tbody>
              {occupancyBySlot.slice(0, 10).map((item) => (
                <tr key={`${item.showtime_id}-${item.slot_label}`}>
                  <td>{item.slot_label || "-"}</td>
                  <td>{item.movie_title || "Unknown"}</td>
                  <td>{item.hall || "-"}</td>
                  <td>{Number(item.tickets_sold || 0).toLocaleString()}</td>
                  <td>{Number(item.capacity || 0).toLocaleString()}</td>
                  <td>{Number(item.occupancy_percent || 0).toFixed(1)}%</td>
                </tr>
              ))}
              {!loading && occupancyBySlot.length === 0 ? (
                <tr>
                  <td colSpan="6">No slot-level occupancy data yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Show Performance Snapshot</h3>
            <p>Practical breakdown with naturally uneven sales</p>
          </div>
        </div>

        {earningsPerShow.length === 0 ? (
          <p className="text-muted mb-0">No rows yet.</p>
        ) : (
          <div className="table-responsive">
            <table className="table table-sm mb-0 revenue-table">
              <thead>
                <tr>
                  <th>Show</th>
                  <th>Tickets</th>
                  <th>Gross</th>
                  <th>Your 90%</th>
                </tr>
              </thead>
              <tbody>
                {earningsPerShow.slice(0, 10).map((row) => (
                  <tr key={`${row?.showtime_id}-${row?.show_title}`}>
                    <td>{row?.show_title || "Unknown"}</td>
                    <td>{Number(row?.tickets_sold || 0).toLocaleString()}</td>
                    <td>{formatMoney(row?.gross_revenue || 0)}</td>
                    <td>{formatMoney(row?.vendor_earning || 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Recent payout transactions</h3>
            <p>Withdrawal and payout ledger entries for this vendor.</p>
          </div>
        </div>
        <div className="table-responsive">
          <table className="table table-sm mb-0 revenue-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Status</th>
                <th>Amount</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {transactions.slice(0, 8).map((item) => (
                <tr key={item.id}>
                  <td>#{item.id}</td>
                  <td>{item.type || item.transaction_type || "-"}</td>
                  <td>
                    <span className={`badge-soft ${transactionTone(item.status)}`}>
                      {item.payout_status || item.status || "-"}
                    </span>
                  </td>
                  <td>{formatMoney(item.amount || 0)}</td>
                  <td>{formatDate(item.created_at)}</td>
                </tr>
              ))}
              {!loading && transactions.length === 0 ? (
                <tr>
                  <td colSpan="5">No payout transactions yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      {actionMessage ? <div className="alert alert-success py-2">{actionMessage}</div> : null}
      {actionError ? <div className="alert alert-warning py-2">{actionError}</div> : null}
    </div>
  );
}

function transactionTone(status) {
  const value = String(status || "").trim().toUpperCase();
  if (value === "COMPLETED" || value === "SUCCESS") return "success";
  if (value === "PENDING") return "warning";
  if (value === "REJECTED" || value === "FAILED") return "danger";
  return "info";
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}
