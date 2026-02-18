import {
  Users,
  Ticket,
  Store,
  Wallet,
  TrendingUp,
  TrendingDown,
  Activity,
  Sparkles,
} from "lucide-react";

const stats = [
  { label: "Total Users", value: "11,580", delta: "+5.9%", icon: Users, tone: "success" },
  { label: "Total Orders", value: "45,580", delta: "+10.9%", icon: Ticket, tone: "info" },
  { label: "Total Vendors", value: "8,580", delta: "-3.9%", icon: Store, tone: "danger" },
  { label: "Total Earnings", value: "$51,580", delta: "+5.9%", icon: Wallet, tone: "success" },
];

const activities = [
  {
    title: "Your account is logged in",
    description: "Activity recorded for vendor access this morning.",
    time: "45 min ago",
    avatar: "JS",
  },
  {
    title: "Current language changed",
    description: "Language switched to English for the dashboard view.",
    time: "1 hour ago",
    avatar: "WL",
  },
  {
    title: "Asked about this project",
    description: "Vendor assistance ticket opened for schedule support.",
    time: "3 hours ago",
    avatar: "KR",
  },
  {
    title: "Revenue spike detected",
    description: "Ticket sales climbed 12% above last week.",
    time: "5 hours ago",
    avatar: "RV",
  },
];

const bestSelling = [
  {
    id: "#01",
    product: "Premium Combo A",
    category: "Combo",
    brand: "Mero F&B",
    price: "NPR 520",
    stock: 20,
    rating: 4.8,
    orders: 540,
    sales: "NPR 54k",
  },
  {
    id: "#02",
    product: "Family Movie Pack",
    category: "Tickets",
    brand: "Hall A",
    price: "NPR 1,200",
    stock: 12,
    rating: 4.6,
    orders: 410,
    sales: "NPR 41k",
  },
  {
    id: "#03",
    product: "Cheese Popcorn",
    category: "Snacks",
    brand: "Snack Bar",
    price: "NPR 300",
    stock: 38,
    rating: 4.4,
    orders: 365,
    sales: "NPR 31k",
  },
  {
    id: "#04",
    product: "Gold Seat Upgrade",
    category: "Tickets",
    brand: "Hall C",
    price: "NPR 150",
    stock: 42,
    rating: 4.7,
    orders: 312,
    sales: "NPR 24k",
  },
];

export default function VendorDashboard() {
  return (
    <div className="vendor-dashboard">
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3">
        <div>
          <h2 className="mb-1">Vendor Dashboard</h2>
          <p className="text-muted mb-0">
            Overview of the MeroTicket vendor performance and activities.
          </p>
        </div>
      </div>
      <div className="vendor-breadcrumb">
        <span>Dashboard</span>
        <span className="vendor-dot">&#8226;</span>
        <span>Overview</span>
      </div>
      <div className="vendor-stat-grid">
        {stats.map((stat) => {
          const Icon = stat.icon;
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
              <div className={`vendor-stat-delta ${stat.delta.startsWith("-") ? "down" : ""}`}>
                {stat.delta.startsWith("-") ? <TrendingDown size={14} /> : <TrendingUp size={14} />}
                {stat.delta}
              </div>
            </div>
          );
        })}
      </div>

      <div className="vendor-grid-2">
        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Revenue Report</h3>
              <p>Monthly performance, earnings, and expenses</p>
            </div>
            <div className="vendor-filter-row">
              <button type="button" className="vendor-chip muted">6 Month</button>
            </div>
          </div>
          <div className="vendor-legend">
            <div><span className="dot earnings" /> Earnings <strong>3,384.78k</strong></div>
            <div><span className="dot invested" /> Invested <strong>2,690.89k</strong></div>
            <div><span className="dot expenses" /> Expenses <strong>1,980.25k</strong></div>
          </div>
          <div className="vendor-chart">
            <svg viewBox="0 0 600 220" className="vendor-chart-svg" role="img" aria-label="Revenue chart">
              <path
                d="M10 140 C 80 100, 140 170, 200 120 S 320 80, 390 130 S 500 200, 590 120"
                fill="none"
                stroke="#7c3aed"
                strokeWidth="3"
              />
              <path
                d="M10 80 C 90 40, 150 130, 220 110 S 340 60, 420 100 S 520 190, 590 150"
                fill="none"
                stroke="#f97316"
                strokeWidth="3"
              />
              <path
                d="M10 170 C 100 200, 160 120, 230 140 S 350 190, 430 150 S 520 80, 590 110"
                fill="none"
                stroke="#22c55e"
                strokeWidth="3"
              />
            </svg>
          </div>
        </section>

        <section className="vendor-card">
          <div className="vendor-card-header">
            <div>
              <h3>Recent Activity</h3>
              <p>Latest vendor updates</p>
            </div>
            <button type="button" className="vendor-icon-btn subtle">...</button>
          </div>
          <div className="vendor-activity">
            {activities.map((activity) => (
              <div key={activity.title} className="vendor-activity-item">
                <div className="vendor-activity-avatar">{activity.avatar}</div>
                <div>
                  <div className="vendor-activity-title">{activity.title}</div>
                  <div className="vendor-activity-desc">{activity.description}</div>
                </div>
                <div className="vendor-activity-time">{activity.time}</div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>Best Selling</h3>
            <p>Top-performing products and upgrades</p>
          </div>
          <div className="vendor-filter-row">
            <button type="button" className="vendor-chip muted">Easy</button>
            <button type="button" className="vendor-chip muted">Month</button>
            <button type="button" className="vendor-chip muted">10 Rows</button>
          </div>
        </div>
        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Product</th>
                <th>Category</th>
                <th>Brand</th>
                <th>Price</th>
                <th>Stock</th>
                <th>Rating</th>
                <th>Orders</th>
                <th>Sales</th>
              </tr>
            </thead>
            <tbody>
              {bestSelling.map((row) => (
                <tr key={row.id}>
                  <td>{row.id}</td>
                  <td className="fw-semibold">{row.product}</td>
                  <td>{row.category}</td>
                  <td>{row.brand}</td>
                  <td>{row.price}</td>
                  <td>{row.stock}</td>
                  <td>{row.rating}</td>
                  <td>{row.orders}</td>
                  <td>{row.sales}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
