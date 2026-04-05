import { useState, useEffect, useRef } from "react";
import {
  Users,
  Ticket,
  Store,
  Wallet,
  TrendingUp,
  TrendingDown,
  ShoppingCart,
  DollarSign,
  Zap,
  BarChart3,
} from "lucide-react";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  AreaChart,
  Area,
} from "recharts";
import { fetchNotifications, fetchVendorAnalytics, markNotificationsRead } from "../lib/catalogApi";

export default function VendorDashboard() {
  const POLL_INTERVAL_MS = 15000;
  const loadAnalyticsRef = useRef(null);
  const loadNotificationsRef = useRef(null);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cancelNotifications, setCancelNotifications] = useState([]);
  const [notificationError, setNotificationError] = useState("");
  const [markingNoticeId, setMarkingNoticeId] = useState(0);

  useEffect(() => {
    let active = true;

    const run = async ({ background = false } = {}) => {
      try {
        if (!background) {
          setLoading(true);
          setError("");
        }
        const data = await fetchVendorAnalytics();
        if (!active) return;
        setAnalytics(data);
        setError("");
      } catch (err) {
        if (!active) return;
        setError(err.message || "Failed to load analytics");
        console.error("Analytics error:", err);
      } finally {
        if (!background && active) {
          setLoading(false);
        }
      }
    };

    loadAnalyticsRef.current = run;
    run({ background: false });

    const loadCancelNotifications = async () => {
      try {
        const payload = await fetchNotifications({ limit: 20, unread: "false" });
        if (!active) return;
        const rows = Array.isArray(payload?.notifications) ? payload.notifications : [];
        const cancelRows = rows
          .filter(
            (item) =>
              String(item?.event_type || "").toUpperCase() === "BOOKING_CANCEL_REQUEST"
          )
          .slice(0, 6);
        setCancelNotifications(cancelRows);
        setNotificationError("");
      } catch (err) {
        if (!active) return;
        setCancelNotifications([]);
        setNotificationError(err?.message || "Unable to load cancellation notifications.");
      }
    };

    loadNotificationsRef.current = loadCancelNotifications;
    loadCancelNotifications();

    const intervalId = setInterval(() => {
      if (document.visibilityState === "visible") {
        run({ background: true });
        loadCancelNotifications();
      }
    }, POLL_INTERVAL_MS);

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        run({ background: true });
        loadCancelNotifications();
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      active = false;
      clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  const loadAnalytics = async () => {
    if (typeof loadAnalyticsRef.current === "function") {
      await loadAnalyticsRef.current({ background: false });
    }
  };

  const loadCancelNotifications = async () => {
    if (typeof loadNotificationsRef.current === "function") {
      await loadNotificationsRef.current();
    }
  };

  const markNotificationAsRead = async (id) => {
    const notificationId = Number(id || 0);
    if (!notificationId || markingNoticeId === notificationId) return;
    setMarkingNoticeId(notificationId);
    try {
      await markNotificationsRead({ ids: [notificationId] });
      await loadCancelNotifications();
    } catch (err) {
      setNotificationError(err?.message || "Unable to mark notification as read.");
    } finally {
      setMarkingNoticeId(0);
    }
  };

  if (loading) {
    return (
      <div className="vendor-dashboard">
        <div className="text-center py-5">
          <div className="spinner-border" role="status">
            <span className="visually-hidden">Loading...</span>
          </div>
        </div>
      </div>
    );
  }

  if (!analytics) {
    return (
      <div className="vendor-dashboard">
        <div className="alert alert-danger">
          {error || "Failed to load analytics data"}
        </div>
        <button className="btn btn-primary" onClick={loadAnalytics}>
          Retry
        </button>
      </div>
    );
  }

  const summary = analytics.summary || {};
  const paymentMethods = analytics.payment_methods || {};
  const bookingStatus = analytics.booking_status_breakdown || {};
  const topFoodItems = analytics.top_food_items || [];
  const topShows = analytics.top_shows || [];
  const recentBookings = analytics.recent_bookings || [];
  const monthlyTrend = analytics.monthly_trend || [];
  const foodByCategory = analytics.food_by_category || [];
  const weeklyBookings = analytics.weekly_bookings || [];
  const bookingValueStats = analytics.booking_value_stats || {};
  const revenuePerShow = analytics.revenue_per_show || [];
  const dropoffSummary = analytics.dropoff_summary || {};
  const dropoffTrend = analytics.dropoff_trend || [];

  const COLORS = ["#10b981", "#f59e0b", "#3b82f6", "#ef4444", "#8b5cf6", "#ec4899"];

  // Build dynamic stats cards
  const stats = [
    {
      label: "Total Bookings",
      value: summary.total_bookings || 0,
      delta: `${summary.confirmed_bookings || 0} Confirmed`,
      icon: Ticket,
      tone: "success",
    },
    {
      label: "Total Revenue",
      value: `NPR ${(summary.total_revenue || 0).toLocaleString("en-US", {
        maximumFractionDigits: 0,
      })}`,
      delta: `${paymentMethods.eSewa?.count || 0} eSewa Sales`,
      icon: Wallet,
      tone: "info",
    },
    {
      label: "Seats Booked",
      value: summary.total_seats_booked || 0,
      delta: `${summary.seat_utilization_percentage || 0}% Occupied`,
      icon: Store,
      tone: "warning",
    },
    {
      label: "Food Sales",
      value: summary.total_food_items_sold || 0,
      delta: `${topFoodItems.length} Menu Items`,
      icon: ShoppingCart,
      tone: "danger",
    },
    {
      label: "Drop-offs",
      value: Number(dropoffSummary.total_left || 0),
      delta: `${Number(dropoffSummary.payment_process_left || 0)} Payment exits`,
      icon: TrendingDown,
      tone: "warning",
    },
  ];

  return (
    <div className="vendor-dashboard">
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3 mb-4">
        <div>
          <h2 className="mb-1">Vendor Dashboard</h2>
          <p className="text-muted mb-0">
            Real-time analytics and performance metrics for {analytics.vendor_name || "your cinema"}
          </p>
        </div>
        <button
          className="btn btn-sm btn-outline-secondary"
          onClick={loadAnalytics}
        >
          <Zap size={14} className="me-2" />
          Refresh
        </button>
      </div>

      {error ? (
        <div className="alert alert-warning py-2 mb-3">
          Live refresh failed: {error}
        </div>
      ) : null}

      <div className="vendor-breadcrumb mb-4">
        <span>Dashboard</span>
        <span className="vendor-dot">&#8226;</span>
        <span>Analytics</span>
      </div>

      {/* Key Metrics Grid */}
      <div className="vendor-stat-grid">
        {stats.map((stat) => {
          const Icon = stat.icon;
          const isPositive = !stat.delta.startsWith("-");
          return (
            <div key={stat.label} className={`vendor-stat ${stat.tone}`}>
              <div className="vendor-stat-row">
                <div>
                  <div className="vendor-stat-value">{stat.value}</div>
                  <div className="vendor-stat-label">{stat.label}</div>
                </div>
                <div className="vendor-stat-icon">
                  <Icon size={18} />
                </div>
              </div>
              <div
                className={`vendor-stat-delta ${isPositive ? "" : "down"}`}
              >
                {isPositive ? (
                  <TrendingUp size={14} />
                ) : (
                  <TrendingDown size={14} />
                )}
                {stat.delta}
              </div>
            </div>
          );
        })}
      </div>

      {/* Main Analytics Sections */}
      <div className="vendor-grid-2">
        {/* Booking Status Breakdown */}
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Booking Status</h3>
              <p>Current booking distribution</p>
            </div>
          </div>
          {Object.entries(bookingStatus).length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={Object.entries(bookingStatus).map(([name, value]) => ({
                    name,
                    value,
                  }))}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, value }) => `${name}: ${value}`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {["Pending", "Confirmed", "Completed", "Cancelled"].map(
                    (status, idx) => {
                      const colors = {
                        Pending: "#f59e0b",
                        Confirmed: "#10b981",
                        Completed: "#3b82f6",
                        Cancelled: "#ef4444",
                      };
                      return (
                        <Cell
                          key={`cell-${idx}`}
                          fill={colors[status] || "#8884d8"}
                        />
                      );
                    }
                  )}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-muted">No booking data available</p>
          )}
        </section>

        {/* Payment Methods */}
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Payment Methods</h3>
              <p>Revenue by payment type</p>
            </div>
          </div>
          {Object.entries(paymentMethods).length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart
                data={Object.entries(paymentMethods).map(([name, data]) => ({
                  name,
                  revenue: data.total || 0,
                  transactions: data.count || 0,
                }))}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.1)" />
                <XAxis dataKey="name" stroke="rgba(0,0,0,0.5)" />
                <YAxis stroke="rgba(0,0,0,0.5)" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#fff",
                    border: "1px solid #ccc",
                    borderRadius: "8px",
                  }}
                  formatter={(value) => `NPR ${value.toLocaleString()}`}
                />
                <Legend />
                <Bar
                  dataKey="revenue"
                  fill="#10b981"
                  name="Revenue (NPR)"
                  radius={[8, 8, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-muted">No payment transactions yet</p>
          )}
        </section>
      </div>

      {/* Top Shows & Food */}
      <div className="vendor-grid-2">
        {/* Top Shows */}
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Top Shows</h3>
              <p>Most booked movies</p>
            </div>
          </div>
          {topShows.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={topShows}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.1)" />
                <XAxis
                  dataKey="title"
                  stroke="rgba(0,0,0,0.5)"
                  angle={-45}
                  textAnchor="end"
                  height={100}
                />
                <YAxis stroke="rgba(0,0,0,0.5)" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#fff",
                    border: "1px solid #ccc",
                    borderRadius: "8px",
                  }}
                />
                <Legend />
                <Bar
                  dataKey="bookings"
                  fill="#3b82f6"
                  name="Bookings"
                  radius={[8, 8, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-muted">No show data available</p>
          )}
        </section>

        {/* Top Food Items */}
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Top Food Items</h3>
              <p>Best-selling food & beverages</p>
            </div>
          </div>
          {topFoodItems.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={topFoodItems}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.1)" />
                <XAxis
                  dataKey="name"
                  stroke="rgba(0,0,0,0.5)"
                  angle={-45}
                  textAnchor="end"
                  height={100}
                />
                <YAxis stroke="rgba(0,0,0,0.5)" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#fff",
                    border: "1px solid #ccc",
                    borderRadius: "8px",
                  }}
                />
                <Legend />
                <Bar
                  dataKey="quantity"
                  fill="#f59e0b"
                  name="Units Sold"
                  radius={[8, 8, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-muted">No food sales yet</p>
          )}
        </section>
      </div>

      {/* Monthly Trend Chart */}
      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Monthly Trend</h3>
            <p>Booking and revenue trend (Last 30 days)</p>
          </div>
        </div>
        {monthlyTrend.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={monthlyTrend}>
              <defs>
                <linearGradient id="colorBookings" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="colorRevenue" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.1)" />
              <XAxis dataKey="date" stroke="rgba(0,0,0,0.5)" />
              <YAxis stroke="rgba(0,0,0,0.5)" />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#fff",
                  border: "1px solid #ccc",
                  borderRadius: "8px",
                }}
              />
              <Legend />
              <Area
                type="monotone"
                dataKey="bookings"
                stroke="#10b981"
                fillOpacity={1}
                fill="url(#colorBookings)"
                name="Bookings"
              />
              <Area
                type="monotone"
                dataKey="revenue"
                stroke="#3b82f6"
                fillOpacity={1}
                fill="url(#colorRevenue)"
                name="Revenue (NPR)"
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-muted">No trend data available</p>
        )}
      </section>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Booking Drop-off Trend</h3>
            <p>Users leaving booking and payment process</p>
          </div>
          <div className="d-flex gap-2">
            <span className="badge text-bg-warning">
              Booking: {Number(dropoffSummary.booking_process_left || 0)}
            </span>
            <span className="badge text-bg-danger">
              Payment: {Number(dropoffSummary.payment_process_left || 0)}
            </span>
          </div>
        </div>
        {dropoffTrend.length > 0 ? (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={dropoffTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--vendor-border)" />
              <XAxis dataKey="date" stroke="var(--vendor-muted)" />
              <YAxis stroke="var(--vendor-muted)" />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--vendor-panel)",
                  border: "1px solid var(--vendor-border)",
                  color: "var(--vendor-text)",
                  borderRadius: "8px",
                }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="booking_process_left"
                stroke="#f59e0b"
                strokeWidth={2}
                name="Booking Process"
                dot={{ r: 3 }}
              />
              <Line
                type="monotone"
                dataKey="payment_process_left"
                stroke="#ef4444"
                strokeWidth={2}
                name="Payment Process"
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-muted">No drop-off data available</p>
        )}
      </section>

      {/* Customer cancellation request notifications */}
      <section className="vendor-card mt-4">
        <div className="vendor-card-header">
          <div>
            <h3>Cancellation Requests</h3>
            <p>Requests sent by customers from their booking page</p>
          </div>
          <button
            type="button"
            className="btn btn-sm btn-outline-secondary"
            onClick={loadCancelNotifications}
          >
            Refresh requests
          </button>
        </div>

        {notificationError ? (
          <div className="alert alert-warning py-2 mb-3">{notificationError}</div>
        ) : null}

        {cancelNotifications.length === 0 ? (
          <p className="text-muted mb-0">No cancellation request notifications yet.</p>
        ) : (
          <div className="table-responsive">
            <table className="table table-sm align-middle mb-0">
              <thead>
                <tr>
                  <th>Booking</th>
                  <th>Status</th>
                  <th>Message</th>
                  <th>Time</th>
                  <th className="text-end">Action</th>
                </tr>
              </thead>
              <tbody>
                {cancelNotifications.map((item) => {
                  const metadata = item?.metadata && typeof item.metadata === "object" ? item.metadata : {};
                  const bookingId = metadata?.booking_id || "-";
                  const requestStatus = String(metadata?.request_status || "PENDING").toUpperCase();
                  const createdAt = item?.created_at ? new Date(item.created_at) : null;
                  const createdLabel =
                    createdAt && !Number.isNaN(createdAt.getTime())
                      ? createdAt.toLocaleString()
                      : "-";
                  return (
                    <tr key={item?.id || `${bookingId}-${createdLabel}`}>
                      <td>#{bookingId}</td>
                      <td>
                        <span className={`badge ${requestStatus === "PENDING" ? "text-bg-warning" : "text-bg-secondary"}`}>
                          {requestStatus}
                        </span>
                      </td>
                      <td>{item?.message || "Cancellation request"}</td>
                      <td>{createdLabel}</td>
                      <td className="text-end">
                        {item?.is_read ? (
                          <span className="text-muted">Read</span>
                        ) : (
                          <button
                            type="button"
                            className="btn btn-sm btn-outline-primary"
                            onClick={() => markNotificationAsRead(item?.id)}
                            disabled={markingNoticeId === item?.id}
                          >
                            {markingNoticeId === item?.id ? "Updating..." : "Mark read"}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <h5 style={{ marginTop: "40px", fontSize: "1.1rem", fontWeight: "600", color: "var(--vendor-text)" }}>
        Advanced Analytics
      </h5>

      {/* Food & Revenue Analytics */}
      <div className="vendor-grid-2">
        {/* Food Category Distribution */}
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Food Sales by Category</h3>
              <p>Revenue breakdown by category</p>
            </div>
          </div>
          {foodByCategory.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={foodByCategory}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--vendor-border)" />
                <XAxis dataKey="name" stroke="var(--vendor-muted)" angle={-45} textAnchor="end" height={100} />
                <YAxis stroke="var(--vendor-muted)" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--vendor-panel)",
                    border: "1px solid var(--vendor-border)",
                    color: "var(--vendor-text)",
                    borderRadius: "8px",
                  }}
                  formatter={(value) => `${value} units`}
                />
                <Legend />
                <Bar dataKey="quantity" fill="#a855f7" name="Units Sold" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-muted">No food sales data</p>
          )}
        </section>

        {/* Weekly Booking Pattern */}
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Bookings by Day</h3>
              <p>Weekly booking distribution</p>
            </div>
          </div>
          {weeklyBookings.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={weeklyBookings}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--vendor-border)" />
                <XAxis dataKey="day" stroke="var(--vendor-muted)" />
                <YAxis stroke="var(--vendor-muted)" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--vendor-panel)",
                    border: "1px solid var(--vendor-border)",
                    color: "var(--vendor-text)",
                    borderRadius: "8px",
                  }}
                />
                <Bar dataKey="bookings" fill="#06b6d4" name="Bookings" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-muted">No weekly data available</p>
          )}
        </section>
      </div>

      {/* Revenue & Performance Analytics */}
      <div className="vendor-grid-2">
        {/* Revenue per Show */}
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Top Performing Shows</h3>
              <p>Revenue by show/movie</p>
            </div>
          </div>
          {revenuePerShow.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={revenuePerShow}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--vendor-border)" />
                <XAxis
                  dataKey="show"
                  stroke="var(--vendor-muted)"
                  angle={-45}
                  textAnchor="end"
                  height={100}
                  fontSize={12}
                />
                <YAxis stroke="var(--vendor-muted)" />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--vendor-panel)",
                    border: "1px solid var(--vendor-border)",
                    color: "var(--vendor-text)",
                    borderRadius: "8px",
                  }}
                  formatter={(value) => `NPR ${value.toLocaleString()}`}
                />
                <Legend />
                <Bar dataKey="revenue" fill="#14b8a6" name="Revenue (NPR)" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-muted">No show revenue data</p>
          )}
        </section>

        {/* Booking Value Analysis */}
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Booking Value Analysis</h3>
              <p>Average transaction metrics</p>
            </div>
          </div>
          <div style={{ padding: "20px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "15px" }}>
            <div style={{ padding: "15px", background: "rgba(16, 185, 129, 0.1)", borderRadius: "8px" }}>
              <div style={{ fontSize: "0.85rem", color: "var(--vendor-muted)", marginBottom: "5px" }}>
                Average Value
              </div>
              <div style={{ fontSize: "1.5rem", fontWeight: "600", color: "#10b981" }}>
                NPR {(bookingValueStats.avg_value || 0).toFixed(0).toLocaleString()}
              </div>
            </div>
            <div style={{ padding: "15px", background: "rgba(59, 130, 246, 0.1)", borderRadius: "8px" }}>
              <div style={{ fontSize: "0.85rem", color: "var(--vendor-muted)", marginBottom: "5px" }}>
                Highest Booking
              </div>
              <div style={{ fontSize: "1.5rem", fontWeight: "600", color: "#3b82f6" }}>
                NPR {(bookingValueStats.max_value || 0).toFixed(0).toLocaleString()}
              </div>
            </div>
            <div style={{ padding: "15px", background: "rgba(239, 68, 68, 0.1)", borderRadius: "8px" }}>
              <div style={{ fontSize: "0.85rem", color: "var(--vendor-muted)", marginBottom: "5px" }}>
                Lowest Booking
              </div>
              <div style={{ fontSize: "1.5rem", fontWeight: "600", color: "#ef4444" }}>
                NPR {(bookingValueStats.min_value || 0).toFixed(0).toLocaleString()}
              </div>
            </div>
            <div style={{ padding: "15px", background: "rgba(168, 85, 247, 0.1)", borderRadius: "8px" }}>
              <div style={{ fontSize: "0.85rem", color: "var(--vendor-muted)", marginBottom: "5px" }}>
                Avg Food/Booking
              </div>
              <div style={{ fontSize: "1.5rem", fontWeight: "600", color: "#a855f7" }}>
                {((summary.total_food_items_sold || 0) / (summary.total_bookings || 1)).toFixed(1)}
              </div>
            </div>
          </div>
        </section>
      </div>

      {/* Advanced Analytics Section */}
      <h5 style={{ marginTop: "40px", fontSize: "1.1rem", fontWeight: "600", color: "var(--vendor-text)" }}>
        Performance Analytics
      </h5>

      {/* Revenue Trend Line Chart */}
      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Monthly Trend</h3>
            <p>30-day revenue and booking trend</p>
          </div>
        </div>
        {monthlyTrend.length > 0 ? (
          <ResponsiveContainer width="100%" height={350}>
            <LineChart data={monthlyTrend}>
              <defs>
                <linearGradient id="colorRev" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--vendor-border)" />
              <XAxis dataKey="date" stroke="var(--vendor-muted)" />
              <YAxis stroke="var(--vendor-muted)" />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--vendor-panel)",
                  border: "1px solid var(--vendor-border)",
                  color: "var(--vendor-text)",
                  borderRadius: "8px",
                }}
                formatter={(value, name) => {
                  if (name === "revenue") return [`NPR ${value.toLocaleString()}`, "Revenue"];
                  return [value, "Bookings"];
                }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="revenue"
                stroke="#3b82f6"
                dot={{ fill: "#3b82f6", r: 4 }}
                activeDot={{ r: 6 }}
                name="Revenue (NPR)"
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="bookings"
                stroke="#10b981"
                dot={{ fill: "#10b981", r: 4 }}
                activeDot={{ r: 6 }}
                name="Bookings"
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-muted">No trend data available</p>
        )}
      </section>

      {/* Revenue & Seat Utilization Comparison */}
      <div className="vendor-grid-2">
        {/* Seat Utilization Gauge */}
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Seat Utilization</h3>
              <p>Current occupancy rate</p>
            </div>
          </div>
          <div
            style={{
              padding: "40px 20px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div
              style={{
                width: "140px",
                height: "140px",
                borderRadius: "50%",
                background: `conic-gradient(#10b981 0deg ${(summary.seat_utilization_percentage || 0) * 3.6}deg, var(--vendor-border) 0deg)`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                position: "relative",
                marginBottom: "20px",
              }}
            >
              <div
                style={{
                  width: "120px",
                  height: "120px",
                  borderRadius: "50%",
                  background: "var(--vendor-panel)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexDirection: "column",
                }}
              >
                <div style={{ fontSize: "2rem", fontWeight: "bold", color: "#10b981" }}>
                  {(summary.seat_utilization_percentage || 0).toFixed(1)}%
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--vendor-muted)" }}>Occupied</div>
              </div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "0.9rem", color: "var(--vendor-text)", marginBottom: "5px" }}>
                {summary.total_seats_booked || 0} seats booked
              </div>
              <div style={{ fontSize: "0.85rem", color: "var(--vendor-muted)" }}>
                Performance is good
              </div>
            </div>
          </div>
        </section>

        {/* Food Revenue by Category */}
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Food Sales Distribution</h3>
              <p>Revenue by category</p>
            </div>
          </div>
          {foodByCategory.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={foodByCategory}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={({ name, quantity }) => `${name}: ${quantity}`}
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="revenue"
                >
                  {foodByCategory.map((entry, index) => (
                    <Cell key={`food-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--vendor-panel)",
                    border: "1px solid var(--vendor-border)",
                    color: "var(--vendor-text)",
                    borderRadius: "8px",
                  }}
                  formatter={(value) => `NPR ${value.toLocaleString()}`}
                />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-muted">No food sales data</p>
          )}
        </section>
      </div>

      {/* Composite Performance Chart */}
      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Booking & Revenue Correlation</h3>
            <p>Weekly performance metrics</p>
          </div>
        </div>
        {weeklyBookings.length > 0 ? (
          <ResponsiveContainer width="100%" height={350}>
            <AreaChart data={weeklyBookings}>
              <defs>
                <linearGradient id="colorBookings" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--vendor-border)" />
              <XAxis dataKey="day" stroke="var(--vendor-muted)" />
              <YAxis stroke="var(--vendor-muted)" />
              <Tooltip
                contentStyle={{
                  backgroundColor: "var(--vendor-panel)",
                  border: "1px solid var(--vendor-border)",
                  color: "var(--vendor-text)",
                  borderRadius: "8px",
                }}
              />
              <Area
                type="monotone"
                dataKey="bookings"
                stroke="#10b981"
                fillOpacity={1}
                fill="url(#colorBookings)"
                name="Bookings"
                dot={{ fill: "#10b981", r: 4 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-muted">No weekly data available</p>
        )}
      </section>

      {/* Revenue Metrics Cards */}
      <div className="vendor-grid-2">
        {/* Revenue Metrics */}
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Revenue Metrics</h3>
              <p>Financial analytics summary</p>
            </div>
          </div>
          <div style={{ padding: "20px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "15px" }}>
            <div style={{ padding: "15px", background: "rgba(16, 185, 129, 0.1)", borderRadius: "8px" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--vendor-muted)", marginBottom: "5px", textTransform: "uppercase" }}>
                Total Revenue
              </div>
              <div style={{ fontSize: "1.4rem", fontWeight: "700", color: "#10b981" }}>
                NPR {(summary.total_revenue || 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}
              </div>
            </div>
            <div style={{ padding: "15px", background: "rgba(59, 130, 246, 0.1)", borderRadius: "8px" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--vendor-muted)", marginBottom: "5px", textTransform: "uppercase" }}>
                Avg Per Booking
              </div>
              <div style={{ fontSize: "1.4rem", fontWeight: "700", color: "#3b82f6" }}>
                NPR {(summary.total_revenue / Math.max(summary.total_bookings, 1)).toLocaleString("en-US", { maximumFractionDigits: 0 })}
              </div>
            </div>
            <div style={{ padding: "15px", background: "rgba(249, 158, 11, 0.1)", borderRadius: "8px" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--vendor-muted)", marginBottom: "5px", textTransform: "uppercase" }}>
                Confirmed Bookings
              </div>
              <div style={{ fontSize: "1.4rem", fontWeight: "700", color: "#f59e0b" }}>
                {summary.confirmed_bookings || 0}
              </div>
            </div>
            <div style={{ padding: "15px", background: "rgba(239, 68, 68, 0.1)", borderRadius: "8px" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--vendor-muted)", marginBottom: "5px", textTransform: "uppercase" }}>
                Completion Rate
              </div>
              <div style={{ fontSize: "1.4rem", fontWeight: "700", color: "#ef4444" }}>
                {summary.total_bookings > 0 ? ((summary.completed_bookings / summary.total_bookings) * 100).toFixed(1) : 0}%
              </div>
            </div>
          </div>
        </section>

        {/* Show Performance Comparison */}
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Top Performing Shows</h3>
              <p>Revenue ranking</p>
            </div>
          </div>
          {topShows.length > 0 ? (
            <div style={{ paddingTop: "20px" }}>
              {topShows.slice(0, 5).map((show, idx) => (
                <div
                  key={idx}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    paddingBottom: "12px",
                    borderBottom: idx < 4 ? "1px solid var(--vendor-border)" : "none",
                    marginBottom: "12px",
                  }}
                >
                  <div>
                    <div style={{ fontWeight: "600", color: "var(--vendor-text)", marginBottom: "3px" }}>
                      {idx + 1}. {show.title}
                    </div>
                    <div style={{ fontSize: "0.85rem", color: "var(--vendor-muted)" }}>
                      {show.bookings} bookings
                    </div>
                  </div>
                  <div style={{ fontWeight: "700", color: "#10b981", fontSize: "1.1rem" }}>
                    NPR {(show.revenue || 0).toLocaleString("en-US", { maximumFractionDigits: 0 })}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted">No show data available</p>
          )}
        </section>
      </div>

      {/* Recent Bookings */}
      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Recent Bookings</h3>
            <p>Latest customer bookings</p>
          </div>
        </div>
        {recentBookings.length > 0 ? (
          <div className="vendor-table-wrap">
            <table className="vendor-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Seats</th>
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {recentBookings.map((booking) => (
                  <tr key={booking.id}>
                    <td className="fw-semibold">{booking.user}</td>
                    <td>{booking.seats}</td>
                    <td>
                      NPR{" "}
                      {(booking.total || 0).toLocaleString("en-US", {
                        maximumFractionDigits: 0,
                      })}
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          booking.status === "Confirmed"
                            ? "bg-success"
                            : booking.status === "Pending"
                              ? "bg-warning"
                              : booking.status === "Completed"
                                ? "bg-info"
                                : "bg-danger"
                        }`}
                      >
                        {booking.status}
                      </span>
                    </td>
                    <td>{new Date(booking.date).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-muted">No bookings yet</p>
        )}
      </section>
    </div>
  );
}
