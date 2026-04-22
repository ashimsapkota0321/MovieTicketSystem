import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { Bar, Line } from "react-chartjs-2";
import {
  fetchVendorRevenueAnalytics,
  fetchVendorTicketValidationMonitor,
  fetchVendorSeatLayout,
  fetchVendorWalletBalance,
  fetchVendorWalletTransactions,
} from "../lib/catalogApi";
import "../css/vendorRevenueDashboard.css";

const CATEGORY_KEYS = ["normal", "executive", "premium", "vip"];
const DEFAULT_SEAT_GROUPS = [
  { key: "normal", label: "Normal", rows: ["A", "B", "C", "D"] },
  { key: "executive", label: "Executive", rows: ["E", "F", "G", "H"] },
  { key: "premium", label: "Premium", rows: ["I", "J"] },
  { key: "vip", label: "VIP", rows: ["K", "L"] },
];
const DEFAULT_SEAT_COLS = Array.from({ length: 15 }, (_, i) => i + 1);

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Legend,
  Filler
);

function formatMoney(value) {
  const amount = Number(value || 0);
  return `NPR ${amount.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

const RANGE_OPTIONS = [
  { key: "last_7_days", label: "7 days" },
  { key: "last_30_days", label: "30 days" },
  { key: "last_90_days", label: "90 days" },
];

const MOVIE_PALETTE = [
  "#1D9E75",
  "#2A7BB6",
  "#E38B2C",
  "#845EC2",
  "#D65B7A",
  "#5F8A35",
  "#1888A5",
  "#B36A2E",
];

export default function VendorDashboard() {
  const navigate = useNavigate();
  const [analytics, setAnalytics] = useState(null);
  const [seatLayout, setSeatLayout] = useState(null);
  const [validationRealtime, setValidationRealtime] = useState(null);
  const [wallet, setWallet] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rangeKey, setRangeKey] = useState("last_30_days");
  const [period] = useState("daily");

  const applyWalletPayload = (walletData) => {
    const walletState = walletData?.wallet || walletData || {};
    setWallet(walletState);
  };

  const loadDashboard = async () => {
    try {
      setLoading(true);
      setError("");
      const [revenueData, seatLayoutData, validationData, walletData, txData] = await Promise.all([
        fetchVendorRevenueAnalytics({ range: rangeKey, group: period }),
        fetchVendorSeatLayout().catch(() => null),
        fetchVendorTicketValidationMonitor({ limit: 50 }).catch(() => null),
        fetchVendorWalletBalance(),
        fetchVendorWalletTransactions(),
      ]);
      setAnalytics(revenueData || {});
      setSeatLayout(seatLayoutData || null);
      setValidationRealtime(validationData?.realtime || null);
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

  useEffect(() => {
    loadDashboard();
  }, [rangeKey, period]);

  const summary = analytics?.summary || {};
  const earningsPerShow = Array.isArray(analytics?.earnings_per_show) ? analytics.earnings_per_show : [];
  const occupancyBySlot = Array.isArray(analytics?.occupancy_by_slot) ? analytics.occupancy_by_slot : [];
  const trend = Array.isArray(analytics?.trend) ? analytics.trend : [];
  const cancellationRate = Number(summary?.cancellation_rate || 0);
  const refundRate = Number(summary?.refund_rate || 0);
  const walletBalance = Number(wallet?.balance || 0);
  const availablePayout = Number(wallet?.available_balance ?? wallet?.availableBalance ?? 0);
  const pendingPayoutAmount = Number(wallet?.pending_withdrawals ?? wallet?.pendingWithdrawals ?? 0);
  const payoutPending = Number(summary?.payout_pending || 0);

  const pendingPayouts = useMemo(
    () => transactions.filter((item) => {
      const type = String(item?.type || item?.transaction_type || "").toUpperCase();
      const status = String(item?.status || "").toUpperCase();
      return type.includes("WITHDRAWAL") && status === "PENDING";
    }),
    [transactions]
  );

  const withdrawalRows = useMemo(
    () => transactions
      .filter((item) => {
        const type = String(item?.type || item?.transaction_type || "").toUpperCase();
        return type.includes("WITHDRAWAL");
      })
      .slice(0, 12),
    [transactions]
  );

  const trendData = useMemo(() => {
    return trend.map((point) => ({
      label: String(point?.label || point?.date || "-"),
      value: Number(point?.value || point?.vendor_earning || point?.amount || 0),
    }));
  }, [trend]);

  const movieBars = useMemo(() => {
    const totalsByMovie = earningsPerShow.reduce((acc, item) => {
      const movie = String(item?.movie_title || item?.show_title || "Unknown");
      const current = acc.get(movie) || { movie, earning: 0, gross: 0, tickets: 0 };
      current.earning += Number(item?.vendor_earning || 0);
      current.gross += Number(item?.gross_revenue || 0);
      current.tickets += Number(item?.tickets_sold || 0);
      acc.set(movie, current);
      return acc;
    }, new Map());

    return Array.from(totalsByMovie.values())
      .sort((a, b) => b.gross - a.gross)
      .slice(0, 8)
      .map((item, index) => ({
        ...item,
        color: MOVIE_PALETTE[index % MOVIE_PALETTE.length],
      }));
  }, [earningsPerShow]);

  const withdrawalRequests = pendingPayouts.length;
  const showsWithEarnings = earningsPerShow.filter((item) => Number(item?.vendor_earning || 0) > 0).length;

  const seatInsights = useMemo(() => {
    const seatMap = buildSeatMap(seatLayout);
    const dynamicSeatGroups =
      Array.isArray(seatLayout?.seat_groups) && seatLayout.seat_groups.length
        ? seatLayout.seat_groups
        : DEFAULT_SEAT_GROUPS;
    const dynamicSeatCols =
      Array.isArray(seatLayout?.seat_columns) && seatLayout.seat_columns.length
        ? seatLayout.seat_columns
            .map((value) => Number(value))
            .filter((value) => Number.isInteger(value) && value > 0)
        : DEFAULT_SEAT_COLS;

    const soldSeatSet = new Set(
      [
        ...(Array.isArray(seatLayout?.sold_seats) ? seatLayout.sold_seats : []),
        ...(Array.isArray(seatLayout?.seats) ? seatLayout.seats : [])
          .filter((seat) => String(seat?.status || "").toLowerCase() === "booked")
          .map((seat) => seat.label),
      ]
        .map((seat) => normalizeSeatLabel(seat))
        .filter(Boolean)
    );

    const unavailableSeatSet = new Set(
      [
        ...(Array.isArray(seatLayout?.unavailable_seats) ? seatLayout.unavailable_seats : []),
        ...(Array.isArray(seatLayout?.seats) ? seatLayout.seats : [])
          .filter((seat) => String(seat?.status || "").toLowerCase() === "unavailable")
          .map((seat) => seat.label),
      ]
        .map((seat) => normalizeSeatLabel(seat))
        .filter(Boolean)
    );

    const reservedSeatSet = new Set(
      [
        ...(Array.isArray(seatLayout?.reserved_seats) ? seatLayout.reserved_seats : []),
        ...(Array.isArray(seatLayout?.reservedSeats) ? seatLayout.reservedSeats : []),
      ]
        .map((seat) => normalizeSeatLabel(seat))
        .filter(Boolean)
    );

    const rowStats = [];
    const categoryBuckets = new Map(
      CATEGORY_KEYS.map((key) => [
        key,
        { key, total: 0, booked: 0, reserved: 0, unavailable: 0, available: 0 },
      ])
    );

    dynamicSeatGroups.forEach((group) => {
      const categoryKey = CATEGORY_KEYS.includes(group?.key) ? group.key : "normal";
      const rowsList = Array.isArray(group?.rows) ? group.rows : [];
      rowsList.forEach((rawRow) => {
        const row = normalizeSeatLabel(rawRow);
        if (!row) return;

        const rowBucket = {
          row,
          category: categoryKey,
          total: 0,
          booked: 0,
          reserved: 0,
          unavailable: 0,
          available: 0,
        };

        dynamicSeatCols.forEach((col) => {
          const seatLabel = `${row}${col}`;
          const seat = seatMap.get(normalizeSeatLabel(seatLabel)) || null;
          const status = getVendorSeatStatus(
            seatLabel,
            seat,
            soldSeatSet,
            unavailableSeatSet,
            reservedSeatSet
          );

          rowBucket.total += 1;
          if (status === "seat--sold") rowBucket.booked += 1;
          else if (status === "seat--reserved") rowBucket.reserved += 1;
          else if (status === "seat--unavailable") rowBucket.unavailable += 1;
          else rowBucket.available += 1;
        });

        rowBucket.pressure = rowBucket.total
          ? ((rowBucket.booked + rowBucket.reserved) / rowBucket.total) * 100
          : 0;
        rowStats.push(rowBucket);

        const categoryBucket = categoryBuckets.get(categoryKey);
        if (categoryBucket) {
          categoryBucket.total += rowBucket.total;
          categoryBucket.booked += rowBucket.booked;
          categoryBucket.reserved += rowBucket.reserved;
          categoryBucket.unavailable += rowBucket.unavailable;
          categoryBucket.available += rowBucket.available;
        }
      });
    });

    const totals = rowStats.reduce(
      (acc, row) => ({
        total: acc.total + row.total,
        booked: acc.booked + row.booked,
        reserved: acc.reserved + row.reserved,
        unavailable: acc.unavailable + row.unavailable,
        available: acc.available + row.available,
      }),
      { total: 0, booked: 0, reserved: 0, unavailable: 0, available: 0 }
    );

    const categoryStats = CATEGORY_KEYS.map((key) => {
      const bucket = categoryBuckets.get(key) || {
        key,
        total: 0,
        booked: 0,
        reserved: 0,
        unavailable: 0,
        available: 0,
      };
      const pressure = bucket.total ? ((bucket.booked + bucket.reserved) / bucket.total) * 100 : 0;
      return {
        ...bucket,
        pressure,
      };
    });

    const hotRows = [...rowStats]
      .sort((left, right) => {
        if (right.pressure !== left.pressure) return right.pressure - left.pressure;
        return right.booked - left.booked;
      })
      .slice(0, 5);

    const occupancy = totals.total ? ((totals.booked + totals.reserved) / totals.total) * 100 : 0;

    return {
      totals,
      occupancy,
      rowStats,
      categoryStats,
      hotRows,
    };
  }, [seatLayout]);

  const payoutCards = [
    { label: "Wallet Balance", value: walletBalance },
    { label: "Available Payout", value: availablePayout, highlight: true },
    { label: "Pending Payouts", value: pendingPayoutAmount },
    { label: "Payout Pending", value: payoutPending },
    { label: "Withdrawal Requests", value: withdrawalRequests, count: true },
  ];

  const kpiCards = [
    { label: "Total Earnings (90%)", value: formatMoney(summary?.total_earnings || 0) },
    { label: "Gross Revenue", value: formatMoney(summary?.total_revenue || 0) },
    { label: "Tickets Sold", value: Number(summary?.total_tickets_sold || 0).toLocaleString() },
    { label: "Shows With Earnings", value: Number(showsWithEarnings || 0).toLocaleString() },
    {
      label: "Cancellation Rate",
      value: `${cancellationRate.toFixed(1)}%`,
      isRate: true,
      high: cancellationRate > 30,
    },
    {
      label: "Refund Rate",
      value: `${refundRate.toFixed(1)}%`,
      isRate: true,
      high: false,
    },
  ];

  const earningsLineData = useMemo(
    () => ({
      labels: trendData.map((point) => point.label),
      datasets: [
        {
          label: "Daily Earnings",
          data: trendData.map((point) => point.value),
          borderColor: "#1D9E75",
          backgroundColor: "rgba(29, 158, 117, 0.18)",
          fill: true,
          tension: 0.32,
          pointRadius: 2,
          pointHoverRadius: 4,
        },
      ],
    }),
    [trendData]
  );

  const revenueByMovieData = useMemo(
    () => ({
      labels: movieBars.map((item) => item.movie),
      datasets: [
        {
          label: "Gross Revenue",
          data: movieBars.map((item) => item.gross),
          backgroundColor: movieBars.map((item) => item.color),
          borderRadius: 6,
        },
      ],
    }),
    [movieBars]
  );

  const validationTrendData = useMemo(() => {
    const fallback = Array.from({ length: 24 }, (_, index) => ({
      hour: `${String(index).padStart(2, "0")}:00`,
      total: 0,
      failed: 0,
    }));

    const source = Array.isArray(validationRealtime?.hourlyScanTrend) && validationRealtime.hourlyScanTrend.length
      ? validationRealtime.hourlyScanTrend
      : fallback;

    return {
      labels: source.map((item) => String(item?.hour || "").slice(0, 2)),
      datasets: [
        {
          type: "bar",
          label: "Scans",
          data: source.map((item) => Math.max(0, Number(item?.total || 0))),
          backgroundColor: "rgba(29, 158, 117, 0.22)",
          borderColor: "#1D9E75",
          borderWidth: 1,
          borderRadius: 4,
        },
        {
          type: "line",
          label: "Failed",
          data: source.map((item) => Math.max(0, Number(item?.failed || 0))),
          borderColor: "#D85A30",
          backgroundColor: "rgba(216, 90, 48, 0.12)",
          tension: 0.28,
          pointRadius: 2,
          yAxisID: "y",
        },
      ],
    };
  }, [validationRealtime]);

  const commonChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (context) => formatMoney(context.parsed?.y ?? context.raw ?? 0),
        },
      },
    },
    scales: {
      x: {
        ticks: {
          autoSkip: false,
          maxRotation: 30,
          minRotation: 0,
        },
        grid: { display: false },
      },
      y: {
        ticks: {
          callback: (value) => `NPR ${Number(value).toLocaleString()}`,
        },
      },
    },
  };

  const handleExportCsv = () => {
    const rows = [
      ["Metric", "Value"],
      ["Total Earnings (90%)", summary?.total_earnings || 0],
      ["Gross Revenue", summary?.total_revenue || 0],
      ["Tickets Sold", summary?.total_tickets_sold || 0],
      ["Cancellation Rate", `${cancellationRate.toFixed(1)}%`],
      ["Refund Rate", `${refundRate.toFixed(1)}%`],
      [],
      ["Recent Payout Transactions"],
      ["ID", "Type", "Status", "Amount", "Created"],
      ...transactions.map((item) => [
        item?.id ?? "",
        item?.type || item?.transaction_type || "",
        item?.status || "",
        item?.amount || 0,
        item?.created_at || "",
      ]),
    ];
    const csv = rows
      .map((row) => row.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(","))
      .join("\n");

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `qfx-vendor-revenue-${rangeKey}.csv`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="vendor-dashboard mvd-dashboard">
        <section className="mvd-card">
          <p className="text-muted mb-0">Loading revenue dashboard...</p>
        </section>
      </div>
    );
  }

  return (
    <div className="vendor-dashboard mvd-dashboard">
      <div className="mvd-header">
        <div>
          <h2 className="mb-1">Vendor Revenue Dashboard</h2>
          <p className="text-muted mb-0">QFX Cinema revenue overview with payouts, performance, and risk indicators.</p>
        </div>
        <div className="mvd-header-actions">
          <div className="mvd-range-group" role="group" aria-label="Date range">
            {RANGE_OPTIONS.map((option) => (
              <button
                key={option.key}
                type="button"
                className={`mvd-range-btn ${rangeKey === option.key ? "active" : ""}`}
                onClick={() => setRangeKey(option.key)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <button type="button" className="mvd-btn mvd-btn-primary" onClick={() => navigate("/vendor/withdrawal")}>
            Request Withdrawal
          </button>
          <button type="button" className="mvd-btn mvd-btn-secondary" onClick={handleExportCsv}>
            Export CSV
          </button>
        </div>
      </div>

      {cancellationRate > 30 ? (
        <div className="mvd-alert-warning">
          High cancellation rate: {cancellationRate.toFixed(1)}% of bookings were cancelled — review show scheduling or pricing.
        </div>
      ) : null}

      {error ? <div className="alert alert-warning py-2">{error}</div> : null}

      <section className="mvd-card">
        <div className="mvd-section-head">
          <div>
            <h3>Payout Status</h3>
            <p>Wallet and settlement overview for QFX Cinema.</p>
          </div>
        </div>
        <div className="mvd-payout-grid">
          {payoutCards.map((card) => {
            const isZero = Number(card.value || 0) === 0;
            return (
              <article
                key={card.label}
                className={`mvd-stat-card ${card.highlight ? "highlight" : ""}`}
              >
                <p className="mvd-stat-label">{card.label}</p>
                <p className="mvd-stat-value">
                  {isZero ? (
                    <span className="mvd-all-clear">All clear</span>
                  ) : card.count ? (
                    Number(card.value || 0).toLocaleString()
                  ) : (
                    formatMoney(card.value)
                  )}
                </p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="mvd-kpi-grid">
        {kpiCards.map((item) => {
          return (
            <article key={item.label} className="mvd-card mvd-kpi-card">
              <div className="mvd-kpi-head">
                <p className="mvd-stat-label">{item.label}</p>
                {item.isRate ? (
                  <span className={`mvd-badge ${item.high ? "high" : "good"}`}>
                    {item.high ? "High" : "Good"}
                  </span>
                ) : null}
              </div>
              <p className={`mvd-stat-value ${item.high ? "danger" : ""}`}>
                {item.value}
              </p>
            </article>
          );
        })}
      </section>

      <div className="mvd-chart-grid">
        <section className="mvd-card">
          <div className="mvd-section-head">
            <div>
              <h3>Daily Earnings Trend</h3>
              <p>Teal earnings curve for selected period.</p>
            </div>
          </div>
          <div className="mvd-chart-wrap">
            <Line data={earningsLineData} options={commonChartOptions} />
          </div>
        </section>

        <section className="mvd-card">
          <div className="mvd-section-head">
            <div>
              <h3>Gross Revenue by Movie</h3>
              <p>Grouped by movie title.</p>
            </div>
          </div>
          <div className="mvd-chart-wrap">
            <Bar
              data={revenueByMovieData}
              options={{
                ...commonChartOptions,
                plugins: {
                  ...commonChartOptions.plugins,
                  tooltip: {
                    callbacks: {
                      label: (context) => formatMoney(context.parsed?.y ?? context.raw ?? 0),
                    },
                  },
                },
              }}
            />
          </div>
        </section>
      </div>

      <section className="mvd-card">
        <div className="mvd-section-head">
          <div>
            <h3>Ticket Validation Trend</h3>
            <p>Hourly entry scans and failed attempts from ticket checks.</p>
          </div>
        </div>
        <div className="mvd-chart-wrap">
          <Bar
            data={validationTrendData}
            options={{
              ...commonChartOptions,
              plugins: {
                ...commonChartOptions.plugins,
                legend: { display: true },
                tooltip: {
                  callbacks: {
                    label: (context) => `${context.dataset.label}: ${Number(context.raw || 0).toLocaleString()}`,
                  },
                },
              },
              scales: {
                x: {
                  grid: { display: false },
                  ticks: { maxRotation: 0, minRotation: 0 },
                },
                y: {
                  beginAtZero: true,
                  ticks: {
                    callback: (value) => Number(value).toLocaleString(),
                  },
                },
              },
            }}
          />
        </div>
      </section>

      <section className="mvd-card">
        <div className="mvd-section-head">
          <div>
            <h3>Occupancy by Slot</h3>
            <p>Live occupancy health for each show slot.</p>
          </div>
        </div>
        <div className="mvd-table-scroll">
          <table className="mvd-table">
            <thead>
              <tr>
                <th>Slot datetime</th>
                <th>Movie</th>
                <th>Hall</th>
                <th>Tickets Sold</th>
                <th>Capacity</th>
                <th>Occupancy %</th>
              </tr>
            </thead>
            <tbody>
              {occupancyBySlot.map((item) => {
                const occupancy = Number(item?.occupancy_percent || 0);
                const tone = occupancy < 20 ? "low" : occupancy >= 30 ? "good" : "mid";
                return (
                  <tr key={`${item.showtime_id}-${item.slot_label}`}>
                    <td>{item.slot_label || "-"}</td>
                    <td>{item.movie_title || "Unknown"}</td>
                    <td>{item.hall || "-"}</td>
                    <td>{Number(item.tickets_sold || 0).toLocaleString()}</td>
                    <td>{Number(item.capacity || 0).toLocaleString()}</td>
                    <td>
                      <div className="mvd-occupancy-wrap">
                        <div className="mvd-occupancy-track">
                          <div
                            className={`mvd-occupancy-fill ${tone}`}
                            style={{ width: `${Math.max(0, Math.min(occupancy, 100))}%` }}
                          />
                        </div>
                        <span>{occupancy.toFixed(1)}%</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {occupancyBySlot.length === 0 ? (
                <tr>
                  <td colSpan="6">No slot-level occupancy data yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mvd-card">
        <div className="mvd-section-head">
          <div>
            <h3>Seat Heatmap & Insights</h3>
            <p>Quickly spot crowded rows, weak zones, and category-level pressure.</p>
          </div>
        </div>

        <div className="vendor-seatInsightMetrics">
          <article className="vendor-seatInsightMetric">
            <span>Total Seats</span>
            <strong>{seatInsights.totals.total.toLocaleString()}</strong>
          </article>
          <article className="vendor-seatInsightMetric">
            <span>Occupied (Booked + Reserved)</span>
            <strong>{(seatInsights.totals.booked + seatInsights.totals.reserved).toLocaleString()}</strong>
          </article>
          <article className="vendor-seatInsightMetric">
            <span>Live Occupancy</span>
            <strong>{seatInsights.occupancy.toFixed(1)}%</strong>
          </article>
          <article className="vendor-seatInsightMetric">
            <span>Unavailable</span>
            <strong>{seatInsights.totals.unavailable.toLocaleString()}</strong>
          </article>
        </div>

        <div className="vendor-seatInsightLayout">
          <div className="vendor-seatHeatPanel">
            <div className="vendor-seatHeatHeader">
              <h4>Row Pressure Heatmap</h4>
              <p>Pressure = booked + reserved seats in each row.</p>
            </div>
            <div className="vendor-seatHeatRows">
              {seatInsights.rowStats.map((row) => {
                const tone = row.pressure >= 70 ? "hot" : row.pressure >= 40 ? "warm" : "cool";
                return (
                  <article key={`heat-${row.row}`} className={`vendor-seatHeatRow ${tone}`}>
                    <div className="vendor-seatHeatMeta">
                      <strong>Row {row.row}</strong>
                      <span>{capitalize(row.category)}</span>
                    </div>
                    <div className="vendor-seatHeatTrack">
                      <div
                        className="vendor-seatHeatFill"
                        style={{ width: `${Math.min(100, Math.max(0, row.pressure))}%` }}
                      />
                    </div>
                    <div className="vendor-seatHeatValue">
                      {row.pressure.toFixed(0)}% ({row.booked + row.reserved}/{row.total})
                    </div>
                  </article>
                );
              })}
              {seatInsights.rowStats.length === 0 ? (
                <div className="text-muted">No rows available for heatmap yet.</div>
              ) : null}
            </div>
          </div>

          <aside className="vendor-seatInsightSide">
            <section className="vendor-seatInsightBlock">
              <h4>Category Utilization</h4>
              <div className="vendor-seatCategoryList">
                {seatInsights.categoryStats.map((item) => (
                  <div className="vendor-seatCategoryItem" key={`category-${item.key}`}>
                    <div className="vendor-seatCategoryHead">
                      <span>{capitalize(item.key)}</span>
                      <strong>{item.pressure.toFixed(0)}%</strong>
                    </div>
                    <div className="vendor-seatCategoryTrack">
                      <div
                        className={`vendor-seatCategoryFill ${item.key}`}
                        style={{ width: `${Math.min(100, Math.max(0, item.pressure))}%` }}
                      />
                    </div>
                    <small>
                      {item.booked + item.reserved}/{item.total} occupied
                    </small>
                  </div>
                ))}
              </div>
            </section>

            <section className="vendor-seatInsightBlock">
              <h4>Hot Rows Watchlist</h4>
              <ul className="vendor-seatHotList">
                {seatInsights.hotRows.map((row) => (
                  <li key={`hot-${row.row}`}>
                    <span>Row {row.row}</span>
                    <strong>{row.pressure.toFixed(0)}%</strong>
                  </li>
                ))}
                {seatInsights.hotRows.length === 0 ? (
                  <li>
                    <span className="text-muted">No row activity yet.</span>
                  </li>
                ) : null}
              </ul>
            </section>
          </aside>
        </div>
      </section>

      <section className="mvd-card">
        <div className="mvd-section-head">
          <div>
            <h3>Show Performance Snapshot</h3>
            <p>Settled vs pending show earnings.</p>
          </div>
        </div>
        <div className="mvd-table-scroll">
          <table className="mvd-table">
            <thead>
              <tr>
                <th>Show</th>
                <th>Tickets</th>
                <th>Gross</th>
                <th>Your 90%</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {earningsPerShow.map((row) => {
                const earning = Number(row?.vendor_earning || 0);
                const isPending = earning <= 0;
                return (
                  <tr key={`${row?.showtime_id}-${row?.show_title}`}>
                    <td>{row?.show_title || "Unknown"}</td>
                    <td>{Number(row?.tickets_sold || 0).toLocaleString()}</td>
                    <td>{formatMoney(row?.gross_revenue || 0)}</td>
                    <td>
                      {isPending ? (
                        <span className="mvd-pending-money">NPR 0 - not settled</span>
                      ) : (
                        formatMoney(earning)
                      )}
                    </td>
                    <td>
                      <span className={`mvd-badge ${isPending ? "pending" : "earning"}`}>
                        {isPending ? "Pending" : "Earning"}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {earningsPerShow.length === 0 ? (
                <tr>
                  <td colSpan="5">No rows yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mvd-card">
        <div className="mvd-section-head">
          <div>
            <h3>Recent Payout Transactions</h3>
            <p>Latest wallet transactions and settlement entries.</p>
          </div>
        </div>
        <div className="mvd-table-scroll">
          <table className="mvd-table">
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
              {transactions.slice(0, 12).map((item) => {
                const rowType = String(item?.type || item?.transaction_type || "").toUpperCase();
                const statusText = String(item?.payout_status || item?.status || "-").toUpperCase();
                return (
                  <tr key={item.id}>
                    <td>#{item.id}</td>
                    <td>
                      <span className={rowType === "PLATFORM_COMMISSION" ? "mvd-type-muted" : "mvd-type-primary"}>
                        {rowType || "-"}
                      </span>
                    </td>
                    <td>
                      <span className={`mvd-pill ${statusText === "COMPLETED" ? "completed" : "default"}`}>
                        {statusText || "-"}
                      </span>
                    </td>
                    <td>{formatMoney(item?.amount || 0)}</td>
                    <td>{formatDate(item?.created_at)}</td>
                  </tr>
                );
              })}
              {transactions.length === 0 ? (
                <tr>
                  <td colSpan="5">No payout transactions yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mvd-card">
        <div className="mvd-section-head">
          <div>
            <h3>Withdrawal Requests</h3>
            <p>Latest vendor withdrawal records and their current status.</p>
          </div>
        </div>
        <div className="mvd-table-scroll">
          <table className="mvd-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Status</th>
                <th>Amount</th>
                <th>Requested</th>
              </tr>
            </thead>
            <tbody>
              {withdrawalRows.map((item) => {
                const rowType = String(item?.type || item?.transaction_type || "-").toUpperCase();
                const statusText = String(item?.payout_status || item?.status || "-").toUpperCase();
                const statusClass =
                  statusText === "COMPLETED"
                    ? "completed"
                    : statusText === "PENDING"
                      ? "pending"
                      : statusText === "REJECTED" || statusText === "FAILED"
                        ? "rejected"
                        : "default";
                return (
                  <tr key={`withdraw-${item.id}`}>
                    <td>#{item.id}</td>
                    <td>{rowType}</td>
                    <td>
                      <span className={`mvd-pill ${statusClass}`}>{statusText}</span>
                    </td>
                    <td>{formatMoney(item?.amount || 0)}</td>
                    <td>{formatDate(item?.created_at)}</td>
                  </tr>
                );
              })}
              {withdrawalRows.length === 0 ? (
                <tr>
                  <td colSpan="5">No withdrawal records found.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function formatDate(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function buildSeatMap(layout) {
  const seats = Array.isArray(layout?.seats) ? layout.seats : [];
  const seatMap = new Map();
  seats.forEach((seat) => {
    const row = String(seat.row_label || "").trim().toUpperCase();
    const column = String(seat.seat_number || "").trim();
    if (!row || !column) return;
    seatMap.set(normalizeSeatLabel(`${row}${column}`), seat);
  });
  return seatMap;
}

function normalizeSeatLabel(value) {
  return String(value || "")
    .replace(/\s+/g, "")
    .toUpperCase()
    .trim();
}

function getVendorSeatStatus(key, seat, soldSeatSet, unavailableSeatSet, reservedSeatSet) {
  const normalized = normalizeSeatLabel(key);
  const seatStatus = String(seat?.status || "").toLowerCase();
  if (soldSeatSet.has(normalized) || seatStatus === "booked") return "seat--sold";
  if (unavailableSeatSet.has(normalized) || seatStatus === "unavailable") {
    return "seat--unavailable";
  }
  if (reservedSeatSet?.has?.(normalized) || seatStatus === "reserved") {
    return "seat--reserved";
  }
  return "seat--available";
}

function capitalize(value) {
  const text = String(value || "");
  if (!text) return text;
  return text.charAt(0).toUpperCase() + text.slice(1);
}
