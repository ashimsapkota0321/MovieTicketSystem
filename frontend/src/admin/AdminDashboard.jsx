import { useEffect, useMemo, useState } from "react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ComposedChart,
  Area,
  Legend,
} from "recharts";
import { ShieldCheck, Wallet, Users, Landmark, RefreshCw } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import { fetchAdminRevenueAnalytics } from "../lib/catalogApi";

function formatMoney(value) {
  const amount = Number(value || 0);
  return `NPR ${amount.toLocaleString("en-NP", { maximumFractionDigits: 2 })}`;
}

function formatCount(value) {
  return Number(value || 0).toLocaleString("en-NP");
}

function shortVendorName(value) {
  const text = String(value || "Unknown");
  if (text.length < 15) return text;
  return `${text.slice(0, 15)}...`;
}

export default function AdminDashboard() {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rangeKey, setRangeKey] = useState("last_30_days");
  const [period, setPeriod] = useState("daily");

  const loadDashboard = async () => {
    try {
      setLoading(true);
      setError("");
      const data = await fetchAdminRevenueAnalytics({ range: rangeKey, group: period });
      setAnalytics(data || {});
    } catch (err) {
      setError(err?.message || "Could not load admin revenue analytics.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboard();
  }, [rangeKey, period]);

  const summary = analytics?.summary || {};
  const topVendors = Array.isArray(analytics?.top_performing_vendors) ? analytics.top_performing_vendors : [];
  const displayTrend = useMemo(
    () => (Array.isArray(analytics?.trend) ? analytics.trend : []),
    [analytics?.trend]
  );

  const vendorBarRows = useMemo(() => {
    return topVendors.slice(0, 8).map((row) => ({
      vendor: shortVendorName(row?.vendor_name),
      commission: Number(row?.admin_commission || 0),
      revenue: Number(row?.platform_revenue || 0),
      bookings: Number(row?.bookings || 0),
    }));
  }, [topVendors]);

  const trendTableRows = useMemo(() => {
    return displayTrend.map((row, index) => {
      const revenue = Number(row?.platform_revenue || 0);
      const commission = Number(row?.admin_commission || 0);
      const previousRevenue = Number(displayTrend[index - 1]?.platform_revenue || 0);
      const deltaPercent =
        previousRevenue > 0 ? ((revenue - previousRevenue) / previousRevenue) * 100 : null;

      return {
        label: row?.label || "-",
        revenue,
        commission,
        commissionRate: revenue > 0 ? (commission / revenue) * 100 : 0,
        deltaPercent,
      };
    });
  }, [displayTrend]);

  const statCards = [
    {
      label: "Total Commission (10%)",
      value: formatMoney(summary?.total_commission_earned),
      hint: "From successful ticket sales",
      icon: ShieldCheck,
    },
    {
      label: "Platform Revenue",
      value: formatMoney(summary?.platform_total_revenue),
      hint: "Gross before split",
      icon: Landmark,
    },
    {
      label: "Admin Wallet Balance",
      value: formatMoney(summary?.admin_wallet_balance),
      hint: "Available after reversals",
      icon: Wallet,
    },
    {
      label: "Active Vendors in Range",
      value: topVendors.length,
      hint: "Usually uneven distribution",
      icon: Users,
    },
  ];

  if (loading) {
    return <AdminPageHeader title="Admin Dashboard" subtitle="Loading revenue analytics..." />;
  }

  return (
    <>
      <AdminPageHeader title="Admin Revenue Dashboard" subtitle="Practical split analytics for platform commission and vendor performance." />

      <section className="admin-card revenue-head revenue-head-admin">
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
          <button type="button" className="btn btn-sm btn-outline-light" onClick={loadDashboard}>
            <RefreshCw size={14} className="me-1" />
            Refresh
          </button>
        </div>
      </section>

      {error ? (
        <section className="admin-card" style={{ borderLeft: "3px solid #d64c4c" }}>
          <p className="mb-0 text-danger">{error}</p>
        </section>
      ) : null}

      <section className="admin-grid-3 revenue-stat-grid-admin">
        {statCards.map((card) => {
          const Icon = card.icon;
          return (
            <div key={card.label} className="admin-stat revenue-stat-card-admin">
              <div className="stat-icon">
                <Icon size={18} />
              </div>
              <div className="stat-value">{card.value}</div>
              <div className="stat-meta">
                <span>{card.label}</span>
              </div>
              <div className="revenue-stat-note">{card.hint}</div>
            </div>
          );
        })}
      </section>

      <section className="admin-card">
        <div className="admin-card-header">
          <div>
            <h5 className="mb-1">Main Revenue Performance Chart</h5>
            <small className="text-muted">Primary dashboard view: total revenue and admin commission over time</small>
          </div>
        </div>
        {displayTrend.length === 0 ? (
          <p className="text-muted mb-0">No trend data available.</p>
        ) : (
          <ResponsiveContainer width="100%" height={340}>
            <ComposedChart data={displayTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--admin-border)" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="var(--admin-muted)" />
              <YAxis tick={{ fontSize: 11 }} stroke="var(--admin-muted)" />
              <Tooltip
                contentStyle={{
                  background: "#fff",
                  border: "1px solid var(--admin-border)",
                  borderRadius: "6px",
                }}
                formatter={(value, name) => {
                  if (name === "platform_revenue") return [formatMoney(value), "Platform Revenue"];
                  return [formatMoney(value), "Admin Commission"];
                }}
              />
              <Legend />
              <Area
                type="monotone"
                dataKey="platform_revenue"
                stroke="#2d7ff9"
                fill="#2d7ff9"
                fillOpacity={0.14}
                name="Platform Revenue"
              />
              <Line
                type="monotone"
                dataKey="admin_commission"
                stroke="#1e9e5a"
                strokeWidth={3}
                dot={{ r: 2 }}
                name="Admin Commission"
              />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </section>

      <section className="admin-grid-2 revenue-grid-main-admin">
        <div className="admin-card">
          <div className="admin-card-header">
            <div>
              <h5 className="mb-1">Platform Revenue Trend</h5>
              <small className="text-muted">Includes irregular changes, low days, and sudden rises</small>
            </div>
          </div>
          {displayTrend.length === 0 ? (
            <p className="text-muted mb-0">No trend data available.</p>
          ) : (
            <ResponsiveContainer width="100%" height={290}>
              <LineChart data={displayTrend}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--admin-border)" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="var(--admin-muted)" />
                <YAxis tick={{ fontSize: 11 }} stroke="var(--admin-muted)" />
                <Tooltip
                  contentStyle={{
                    background: "#fff",
                    border: "1px solid var(--admin-border)",
                    borderRadius: "6px",
                  }}
                  formatter={(value, name) => {
                    if (name === "platform_revenue") return [formatMoney(value), "Platform Revenue"];
                    return [formatMoney(value), "Commission"];
                  }}
                />
                <Line dataKey="platform_revenue" stroke="#2d7ff9" strokeWidth={2} dot={{ r: 2 }} name="Revenue" />
                <Line dataKey="admin_commission" stroke="#1e9e5a" strokeWidth={2} dot={{ r: 2 }} name="Commission" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="admin-card">
          <div className="admin-card-header">
            <div>
              <h5 className="mb-1">Revenue Per Vendor</h5>
              <small className="text-muted">Some vendors naturally dominate</small>
            </div>
          </div>
          {vendorBarRows.length === 0 ? (
            <p className="text-muted mb-0">No vendor rows available.</p>
          ) : (
            <ResponsiveContainer width="100%" height={290}>
              <BarChart data={vendorBarRows}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--admin-border)" />
                <XAxis dataKey="vendor" tick={{ fontSize: 11 }} stroke="var(--admin-muted)" />
                <YAxis tick={{ fontSize: 11 }} stroke="var(--admin-muted)" />
                <Tooltip
                  contentStyle={{
                    background: "#fff",
                    border: "1px solid var(--admin-border)",
                    borderRadius: "6px",
                  }}
                  formatter={(value, name) => {
                    if (name === "revenue") return [formatMoney(value), "Revenue"];
                    if (name === "commission") return [formatMoney(value), "Commission"];
                    return [value, "Bookings"];
                  }}
                />
                <Legend />
                <Bar dataKey="revenue" fill="#2d7ff9" radius={[4, 4, 0, 0]} name="Revenue" />
                <Bar dataKey="commission" fill="#1e9e5a" radius={[4, 4, 0, 0]} name="Commission" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </section>

      <section className="admin-card">
        <div className="admin-card-header">
          <div>
            <h5 className="mb-1">Trend Breakdown Table</h5>
            <small className="text-muted">Structured period-level data for comparison and quick review</small>
          </div>
        </div>

        {trendTableRows.length === 0 ? (
          <p className="text-muted mb-0">No trend rows yet.</p>
        ) : (
          <div className="table-responsive">
            <table className="table admin-table revenue-table">
              <thead>
                <tr>
                  <th>Period</th>
                  <th>Platform Revenue</th>
                  <th>Admin Commission</th>
                  <th>Commission Rate</th>
                  <th>Revenue Change</th>
                </tr>
              </thead>
              <tbody>
                {trendTableRows.slice(-12).map((row) => {
                  const tone =
                    row.deltaPercent == null
                      ? "info"
                      : row.deltaPercent >= 0
                        ? "success"
                        : "danger";
                  const deltaLabel =
                    row.deltaPercent == null
                      ? "-"
                      : `${row.deltaPercent >= 0 ? "+" : ""}${row.deltaPercent.toFixed(1)}%`;

                  return (
                    <tr key={row.label}>
                      <td>{row.label}</td>
                      <td>{formatMoney(row.revenue)}</td>
                      <td>{formatMoney(row.commission)}</td>
                      <td>{row.commissionRate.toFixed(2)}%</td>
                      <td>
                        <span className={`badge-soft ${tone}`}>{deltaLabel}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="admin-card">
        <div className="admin-card-header">
          <div>
            <h5 className="mb-1">Top Vendors</h5>
            <small className="text-muted">Uneven split is expected in real operations</small>
          </div>
        </div>

        {topVendors.length === 0 ? (
          <p className="text-muted mb-0">No vendor performance rows yet.</p>
        ) : (
          <div className="table-responsive">
            <table className="table admin-table revenue-table">
              <thead>
                <tr>
                  <th>Vendor</th>
                  <th>Bookings</th>
                  <th>Platform Revenue</th>
                  <th>Vendor 90%</th>
                  <th>Admin 10%</th>
                </tr>
              </thead>
              <tbody>
                {topVendors.slice(0, 10).map((row) => (
                  <tr key={`${row?.vendor_id}-${row?.vendor_name}`}>
                    <td>{row?.vendor_name || "Unknown"}</td>
                    <td>{formatCount(row?.bookings || 0)}</td>
                    <td>{formatMoney(row?.platform_revenue || 0)}</td>
                    <td>{formatMoney(row?.vendor_earning || 0)}</td>
                    <td>{formatMoney(row?.admin_commission || 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
