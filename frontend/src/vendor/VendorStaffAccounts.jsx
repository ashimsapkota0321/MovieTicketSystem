import { useEffect, useMemo, useState } from "react";
import { Briefcase, Search, ShieldCheck, UserPlus, Users } from "lucide-react";
import {
  createVendorStaffAccount,
  fetchVendorStaffAccounts,
  updateVendorStaffAccount,
} from "../lib/catalogApi";

const STAFF_ROLES = [
  { value: "CASHIER", label: "Cashier" },
  { value: "MANAGER", label: "Manager" },
];

const INITIAL_FORM = {
  full_name: "",
  email: "",
  username: "",
  phone_number: "",
  password: "",
  role: "CASHIER",
  is_active: true,
};

export default function VendorStaffAccounts() {
  const [staffAccounts, setStaffAccounts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [form, setForm] = useState(INITIAL_FORM);

  async function loadStaff() {
    setLoading(true);
    setError("");
    try {
      const data = await fetchVendorStaffAccounts();
      setStaffAccounts(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err?.message || "Failed to load staff accounts.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStaff();
  }, []);

  const filteredStaff = useMemo(() => {
    const term = String(query || "").trim().toLowerCase();
    if (!term) return staffAccounts;
    return staffAccounts.filter((item) => {
      const haystack = [
        item.full_name,
        item.email,
        item.username,
        item.phone_number,
        item.role,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [query, staffAccounts]);

  const activeCount = useMemo(
    () => staffAccounts.filter((item) => Boolean(item.is_active)).length,
    [staffAccounts]
  );
  const managerCount = useMemo(
    () => staffAccounts.filter((item) => String(item.role || "").toUpperCase() === "MANAGER").length,
    [staffAccounts]
  );
  const cashierCount = useMemo(
    () => staffAccounts.filter((item) => String(item.role || "").toUpperCase() === "CASHIER").length,
    [staffAccounts]
  );

  const handleInput = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const resetForm = () => {
    setForm(INITIAL_FORM);
  };

  const handleCreate = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await createVendorStaffAccount({
        full_name: form.full_name,
        email: form.email,
        username: form.username || null,
        phone_number: form.phone_number || null,
        password: form.password,
        role: form.role,
        is_active: form.is_active,
      });
      setMessage("Staff account created successfully.");
      resetForm();
      await loadStaff();
    } catch (err) {
      setError(err?.message || "Failed to create staff account.");
    } finally {
      setSaving(false);
    }
  };

  const handleToggleActive = async (item) => {
    setError("");
    setMessage("");
    try {
      await updateVendorStaffAccount(item.id, { is_active: !item.is_active });
      setMessage("Staff account updated.");
      await loadStaff();
    } catch (err) {
      setError(err?.message || "Failed to update staff account.");
    }
  };

  const handleRoleUpdate = async (item, role) => {
    setError("");
    setMessage("");
    try {
      await updateVendorStaffAccount(item.id, { role });
      setMessage("Staff role updated.");
      await loadStaff();
    } catch (err) {
      setError(err?.message || "Failed to update staff role.");
    }
  };

  return (
    <div className="vendor-dashboard">
      <div className="vendor-marketing-hero mb-3">
        <div>
          <p className="vendor-marketing-eyebrow mb-1">Access Control</p>
          <h2 className="mb-1">Staff Accounts</h2>
          <p className="text-muted mb-0">
            Add and control cashier and manager accounts with clear permission boundaries.
          </p>
        </div>
        <div className="vendor-marketing-metrics">
          <div className="vendor-marketing-metric">
            <span>Total Staff</span>
            <strong>{staffAccounts.length}</strong>
          </div>
          <div className="vendor-marketing-metric">
            <span>Active Staff</span>
            <strong>{activeCount}</strong>
          </div>
          <div className="vendor-marketing-metric">
            <span>Managers / Cashiers</span>
            <strong>
              {managerCount} / {cashierCount}
            </strong>
          </div>
        </div>
      </div>

      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3 mb-3">
        <p className="vendor-breadcrumb mb-0">
          <span>Administration</span>
          <span className="vendor-dot">&#8226;</span>
          <span>Staff Accounts</span>
        </p>
      </div>

      {error ? <div className="alert alert-danger mb-3">{error}</div> : null}
      {message ? <div className="alert alert-success mb-3">{message}</div> : null}

      <section className="vendor-card mb-3">
        <div className="vendor-card-header">
          <div>
            <h3>
              <UserPlus size={18} className="me-2" />
              Create Staff Account
            </h3>
            <p>Use unique credentials for each team member and assign the minimum required role.</p>
          </div>
        </div>

        <div className="row g-3 align-items-start">
          <form className="col-lg-8 row g-2" onSubmit={handleCreate}>
            <div className="col-md-6">
              <label className="form-label">Full Name</label>
            <input
              className="form-control"
              type="text"
              value={form.full_name}
              onChange={(event) => handleInput("full_name", event.target.value)}
              required
            />
            </div>
            <div className="col-md-6">
              <label className="form-label">Email</label>
            <input
              className="form-control"
              type="email"
              value={form.email}
              onChange={(event) => handleInput("email", event.target.value)}
              required
            />
            </div>
            <div className="col-md-4">
              <label className="form-label">Username</label>
            <input
              className="form-control"
              type="text"
              value={form.username}
              onChange={(event) => handleInput("username", event.target.value)}
              placeholder="optional"
            />
            </div>
            <div className="col-md-4">
              <label className="form-label">Phone Number</label>
            <input
              className="form-control"
              type="text"
              value={form.phone_number}
              onChange={(event) => handleInput("phone_number", event.target.value)}
              placeholder="optional"
            />
            </div>
            <div className="col-md-4">
              <label className="form-label">Password</label>
            <input
              className="form-control"
              type="password"
              value={form.password}
              onChange={(event) => handleInput("password", event.target.value)}
              minLength={8}
              required
            />
            </div>
            <div className="col-md-6">
              <label className="form-label">Role</label>
            <select
              className="form-select"
              value={form.role}
              onChange={(event) => handleInput("role", event.target.value)}
            >
              {STAFF_ROLES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            </div>
            <div className="col-md-6">
              <label className="form-label">Status</label>
            <select
              className="form-select"
              value={form.is_active ? "active" : "inactive"}
              onChange={(event) => handleInput("is_active", event.target.value === "active")}
            >
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
            </div>
            <div className="col-12 d-flex justify-content-end">
              <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? "Creating..." : "Create Staff Account"}
            </button>
            </div>
          </form>

          <div className="col-lg-4">
            <div className="vendor-staff-role-panel mb-2">
              <h4>
                <Briefcase size={15} className="me-1" />
                Manager Access
              </h4>
              <p>Can manage pricing and campaigns, plus bookings and ticket validation.</p>
            </div>
            <div className="vendor-staff-role-panel">
              <h4>
                <ShieldCheck size={15} className="me-1" />
                Cashier Access
              </h4>
              <p>Can handle bookings and ticket validation only. No pricing controls.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="vendor-card">
        <div className="vendor-card-header">
          <div>
            <h3>
              <Users size={18} className="me-2" />
              Manage Staff
            </h3>
            <p>Toggle account status and adjust role assignments.</p>
          </div>
          <div className="vendor-staff-search">
            <Search size={15} />
            <input
              className="form-control"
              type="text"
              placeholder="Search by name, email, phone, role"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
        </div>
        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Username</th>
                <th>Phone</th>
                <th>Role</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7}>Loading staff accounts...</td>
                </tr>
              ) : filteredStaff.length ? (
                filteredStaff.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <div className="d-flex align-items-center gap-2">
                        <span className="vendor-staff-avatar">{getInitials(item.full_name || item.email)}</span>
                        <div>
                          <div className="fw-semibold">{item.full_name || "-"}</div>
                          <small className="text-muted">ID: #{item.id}</small>
                        </div>
                      </div>
                    </td>
                    <td>{item.email || "-"}</td>
                    <td>{item.username || "-"}</td>
                    <td>{item.phone_number || "-"}</td>
                    <td>
                      <select
                        className="form-select form-select-sm"
                        value={item.role || "CASHIER"}
                        onChange={(event) => handleRoleUpdate(item, event.target.value)}
                      >
                        {STAFF_ROLES.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <span className={`vendor-request-status ${item.is_active ? "approved" : "neutral"}`}>
                        {item.is_active ? "ACTIVE" : "INACTIVE"}
                      </span>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-light"
                        onClick={() => handleToggleActive(item)}
                      >
                        {item.is_active ? "Deactivate" : "Activate"}
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={7}>No staff accounts found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function getInitials(value) {
  const text = String(value || "").trim();
  if (!text) return "S";
  const parts = text.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] || ""}${parts[1][0] || ""}`.toUpperCase();
}
