import { useEffect, useState, useMemo } from "react";
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, ScatterChart, Scatter } from "recharts";
import { TrendingUp, Calendar, Users, Zap, ArrowUpRight, ArrowDownLeft } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import { getAuthHeaders } from "../lib/authSession";
import { API_BASE_URL } from "../lib/apiBase";
import "../css/admin-vendor-analytics.css";

export default function AdminVendorAnalytics() {
  const [analyticsData, setAnalyticsData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState("last_30_days");
  const [selectedVendor, setSelectedVendor] = useState(null);

  useEffect(() => {
    loadAnalytics();
  }, [timeRange]);

  const loadAnalytics = async () => {
    try {
      setLoading(true);
      const response = await fetch(
        `${API_BASE_URL}/admin/vendors/analytics/?time_range=${timeRange}`,
        {
          headers: { Accept: "application/json", ...getAuthHeaders() },
        }
      );
      if (!response.ok) {
        // Fallback data
        setAnalyticsData(generateMockAnalytics());
        return;
      }
      const data = await response.json();
      setAnalyticsData(data);
    } catch (err) {
      // Fallback to mock data
      setAnalyticsData(generateMockAnalytics());
    } finally {
      setLoading(false);
    }
  };

  const revenueHeatmapData = useMemo(() => {
    if (!analyticsData?.vendor_revenue_by_month) return [];
    return analyticsData.vendor_revenue_by_month.map((item) => ({
      vendor: item.vendor_name,
      month: item.month,
      revenue: item.revenue,
      bookings: item.bookings,
      intensity: Math.min(100, (item.revenue / 50000) * 100), // Color intensity 0-100
    }));
  }, [analyticsData]);

  const bookingVolumeByDayOfWeek = useMemo(() => {
    if (!analyticsData?.booking_volume_by_day) return [];
    const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
    return days.map((day, idx) => ({
      day: day.slice(0, 3),
      fullDay: day,
      bookings: analyticsData.booking_volume_by_day[idx] || 0,
    }));
  }, [analyticsData]);

  const vendorPerformanceComparison = useMemo(() => {
    if (!analyticsData?.vendor_performance_metrics) return [];
    return analyticsData.vendor_performance_metrics.slice(0, 10).map((v) => ({
      name: v.vendor_name.split(" ").shift(), // First name
      revenue: v.total_revenue,
      bookings: v.total_bookings,
      avgOccupancy: v.avg_occupancy_percent,
      id: v.vendor_id,
    }));
  }, [analyticsData]);

  const peakHoursData = useMemo(() => {
    if (!analyticsData?.peak_booking_hours) return [];
    return analyticsData.peak_booking_hours.map((h) => ({
      hour: `${h.hour}:00`,
      bookings: h.count,
      revenue: h.revenue,
    }));
  }, [analyticsData]);

  const vendorGrowthTrend = useMemo(() => {
    if (!analyticsData?.vendor_growth_trend) return [];
    return analyticsData.vendor_growth_trend.map((item) => ({
      date: item.date,
      newVendors: item.new_vendors,
      activeVendors: item.active_vendors,
      totalRevenue: item.total_revenue,
    }));
  }, [analyticsData]);

  const occupancyHeatmapData = useMemo(() => {
    if (!analyticsData?.occupancy_by_vendor_slot) return [];
    return analyticsData.occupancy_by_vendor_slot.slice(0, 12).map((item) => ({
      vendor: item.vendor_name,
      slot: `${item.show_time}`,
      occupancy: item.occupancy_percent,
      intensity: item.occupancy_percent,
      revenue: item.slot_revenue,
      capacity: item.capacity,
      sold: item.sold_seats,
    }));
  }, [analyticsData]);

  const formatMoney = (value) => {
    if (!value) return "₹0";
    return `₹${Number(value).toLocaleString("en-IN")}`;
  };

  const getHeatmapColor = (intensity) => {
    if (intensity >= 80) return "#0ec3e0"; // Bright cyan - hot
    if (intensity >= 60) return "#22a06b"; // Green - warm
    if (intensity >= 40) return "#f2d857"; // Yellow - moderate
    if (intensity >= 20) return "#ff9f1c"; // Orange - cool
    return "#e74c3c"; // Red - cold
  };

  return (
    <>
      <AdminPageHeader
        title="Vendor Analytics"
        subtitle="Monitor vendor performance, revenue trends, and booking patterns."
      >
        <div className="d-flex gap-2">
          <select
            className="form-select"
            style={{ maxWidth: "150px" }}
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
          >
            <option value="last_7_days">Last 7 days</option>
            <option value="last_30_days">Last 30 days</option>
            <option value="last_90_days">Last 90 days</option>
            <option value="last_year">Last year</option>
          </select>
        </div>
      </AdminPageHeader>

      {loading ? (
        <div className="admin-card text-center py-5">
          <div className="spinner-border text-primary" role="status">
            <span className="visually-hidden">Loading analytics...</span>
          </div>
        </div>
      ) : (
        <>
          {/* Key Metrics */}
          <div className="admin-metrics-grid mb-4">
            <MetricCard
              label="Total Revenue"
              value={formatMoney(analyticsData?.total_revenue)}
              change={analyticsData?.revenue_change_percent}
              icon={TrendingUp}
            />
            <MetricCard
              label="Total Bookings"
              value={Number(analyticsData?.total_bookings || 0).toLocaleString()}
              change={analyticsData?.booking_change_percent}
              icon={Zap}
            />
            <MetricCard
              label="Active Vendors"
              value={analyticsData?.active_vendors_count}
              change={analyticsData?.vendor_growth_percent}
              icon={Users}
            />
            <MetricCard
              label="Avg Occupancy"
              value={`${Number(analyticsData?.avg_occupancy_percent || 0).toFixed(1)}%`}
              change={analyticsData?.occupancy_change_percent}
              icon={Calendar}
            />
          </div>

          {/* Revenue Heatmap */}
          <div className="admin-card mb-4">
            <div className="admin-card-header">
              <h4 className="mb-0">Revenue Heatmap by Vendor & Month</h4>
              <small className="text-muted">Darker cyan = Higher revenue</small>
            </div>
            <div className="vendor-heatmap-container">
              <table className="vendor-heatmap-table">
                <thead>
                  <tr>
                    <th className="vendor-col">Vendor</th>
                    {["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].map((month) => (
                      <th key={month} className="month-col">
                        {month}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {Array.from(new Set(revenueHeatmapData.map((d) => d.vendor))).map((vendor) => (
                    <tr key={vendor}>
                      <td className="vendor-col vendor-name">{vendor}</td>
                      {["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].map((month) => {
                        const cell = revenueHeatmapData.find((d) => d.vendor === vendor && d.month === month);
                        return (
                          <td
                            key={`${vendor}-${month}`}
                            className="heatmap-cell"
                            style={{ backgroundColor: cell ? getHeatmapColor(cell.intensity) : "#f0f0f0" }}
                            title={cell ? `${vendor} - ${month}: ${formatMoney(cell.revenue)}` : "No data"}
                          >
                            {cell ? `${(cell.revenue / 1000).toFixed(0)}K` : "-"}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Occupancy Heatmap */}
          <div className="admin-card mb-4">
            <div className="admin-card-header">
              <h4 className="mb-0">Occupancy Rate Heatmap</h4>
              <small className="text-muted">Shows seat occupancy by vendor and show time slot</small>
            </div>
            <div className="occupancy-heatmap">
              {occupancyHeatmapData.length > 0 ? (
                <div className="heatmap-grid">
                  {occupancyHeatmapData.map((item) => (
                    <div
                      key={`${item.vendor}-${item.slot}`}
                      className="heatmap-item"
                      style={{
                        backgroundColor: getHeatmapColor(item.intensity),
                      }}
                      title={`${item.vendor}\n${item.slot}\nOccupancy: ${item.occupancy.toFixed(1)}%\nSeats: ${item.sold}/${item.capacity}`}
                    >
                      <div className="heatmap-vendor">{item.vendor.split(" ").shift()}</div>
                      <div className="heatmap-occupancy">{item.occupancy.toFixed(0)}%</div>
                      <div className="heatmap-time">{item.slot}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-muted">No occupancy data available</p>
              )}
            </div>
          </div>

          {/* Peak Hours Chart */}
          <div className="admin-card mb-4">
            <div className="admin-card-header">
              <h4 className="mb-0">Peak Booking Hours</h4>
              <small className="text-muted">Booking volume by hour of day</small>
            </div>
            {peakHoursData.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={peakHoursData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                  <XAxis dataKey="hour" />
                  <YAxis />
                  <Tooltip
                    formatter={(value, name) => {
                      if (name === "bookings") return [value, "Bookings"];
                      if (name === "revenue") return [formatMoney(value), "Revenue"];
                      return value;
                    }}
                  />
                  <Bar dataKey="bookings" fill="#0ec3e0" name="Bookings" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-muted">No data available</p>
            )}
          </div>

          {/* Booking Volume by Day of Week */}
          <div className="admin-card mb-4">
            <div className="admin-card-header">
              <h4 className="mb-0">Weekly Booking Pattern</h4>
              <small className="text-muted">Booking distribution across days of week</small>
            </div>
            {bookingVolumeByDayOfWeek.length > 0 ? (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={bookingVolumeByDayOfWeek}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                  <XAxis dataKey="day" />
                  <YAxis />
                  <Tooltip
                    labelFormatter={(label) => bookingVolumeByDayOfWeek.find((d) => d.day === label)?.fullDay}
                    formatter={(value) => [value, "Bookings"]}
                  />
                  <Bar dataKey="bookings" fill="#22a06b" name="Bookings" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-muted">No data available</p>
            )}
          </div>

          {/* Vendor Performance Comparison */}
          <div className="admin-card mb-4">
            <div className="admin-card-header">
              <h4 className="mb-0">Top Vendor Performance</h4>
              <small className="text-muted">Revenue vs booking volume comparison</small>
            </div>
            {vendorPerformanceComparison.length > 0 ? (
              <ResponsiveContainer width="100%" height={350}>
                <BarChart data={vendorPerformanceComparison}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                  <XAxis dataKey="name" />
                  <YAxis yAxisId="left" />
                  <YAxis yAxisId="right" orientation="right" />
                  <Tooltip
                    formatter={(value, name) => {
                      if (name === "revenue") return [formatMoney(value), "Revenue"];
                      if (name === "bookings") return [value, "Bookings"];
                      if (name === "avgOccupancy") return [`${value.toFixed(1)}%`, "Avg Occupancy"];
                      return value;
                    }}
                  />
                  <Legend />
                  <Bar yAxisId="left" dataKey="revenue" fill="#0ec3e0" name="Revenue" radius={[4, 4, 0, 0]} />
                  <Bar yAxisId="right" dataKey="bookings" fill="#22a06b" name="Bookings" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-muted">No data available</p>
            )}
          </div>

          {/* Growth Trend */}
          <div className="admin-card">
            <div className="admin-card-header">
              <h4 className="mb-0">Vendor Growth Trend</h4>
              <small className="text-muted">Active vendors and total revenue over time</small>
            </div>
            {vendorGrowthTrend.length > 0 ? (
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={vendorGrowthTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                  <XAxis dataKey="date" />
                  <YAxis yAxisId="left" />
                  <YAxis yAxisId="right" orientation="right" />
                  <Tooltip
                    formatter={(value, name) => {
                      if (name === "totalRevenue") return [formatMoney(value), "Revenue"];
                      return value;
                    }}
                  />
                  <Legend />
                  <Line yAxisId="left" type="monotone" dataKey="activeVendors" stroke="#0ec3e0" name="Active Vendors" strokeWidth={2} />
                  <Line yAxisId="right" type="monotone" dataKey="totalRevenue" stroke="#22a06b" name="Revenue" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-muted">No data available</p>
            )}
          </div>
        </>
      )}
    </>
  );
}

function MetricCard({ label, value, change, icon: Icon }) {
  const isPositive = (change || 0) >= 0;
  return (
    <div className="metric-card">
      <div className="metric-header">
        <div className="metric-label">{label}</div>
        <div className="metric-icon">
          <Icon size={20} />
        </div>
      </div>
      <div className="metric-value">{value}</div>
      {change !== null && change !== undefined && (
        <div className={`metric-change ${isPositive ? "positive" : "negative"}`}>
          {isPositive ? <ArrowUpRight size={14} /> : <ArrowDownLeft size={14} />}
          <span>{Math.abs(change).toFixed(1)}%</span>
        </div>
      )}
    </div>
  );
}

function generateMockAnalytics() {
  const vendors = ["Cinema Palace", "Star Halls", "Rajpath Hall", "Premiere Screen", "Galaxy Theatre"];
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"];
  
  return {
    total_revenue: 2450000,
    total_bookings: 15420,
    active_vendors_count: 5,
    avg_occupancy_percent: 72.5,
    revenue_change_percent: 12.5,
    booking_change_percent: 8.3,
    vendor_growth_percent: 5.0,
    occupancy_change_percent: 3.2,
    
    vendor_revenue_by_month: vendors.flatMap(vendor =>
      months.map((month, idx) => ({
        vendor_name: vendor,
        month: month,
        revenue: Math.random() * 80000 + 20000,
        bookings: Math.floor(Math.random() * 500 + 100),
      }))
    ),
    
    booking_volume_by_day: [320, 420, 390, 410, 520, 680, 590],
    
    peak_booking_hours: Array.from({ length: 24 }, (_, i) => ({
      hour: i,
      count: Math.floor(Math.random() * 80 + (i >= 16 && i <= 22 ? 40 : 10)),
      revenue: Math.random() * 50000,
    })),
    
    vendor_performance_metrics: vendors.map(vendor => ({
      vendor_id: Math.random(),
      vendor_name: vendor,
      total_revenue: Math.random() * 500000 + 100000,
      total_bookings: Math.floor(Math.random() * 3000 + 1000),
      avg_occupancy_percent: Math.random() * 30 + 60,
    })),
    
    occupancy_by_vendor_slot: vendors.flatMap(vendor =>
      ["10:00", "13:00", "16:00", "19:00"].map(time => ({
        vendor_name: vendor,
        show_time: time,
        occupancy_percent: Math.random() * 40 + 50,
        capacity: 200,
        sold_seats: Math.floor(Math.random() * 150 + 50),
        slot_revenue: Math.random() * 25000,
      }))
    ),
    
    vendor_growth_trend: Array.from({ length: 10 }, (_, i) => ({
      date: new Date(Date.now() - (10 - i) * 86400000).toISOString().split("T")[0],
      new_vendors: Math.floor(Math.random() * 2),
      active_vendors: 4 + Math.floor(Math.random() * 2),
      total_revenue: Math.random() * 300000 + 150000,
    })),
  };
}
