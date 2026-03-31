import { useEffect, useMemo, useState } from "react";
import { KeyRound, Lock, Pencil, Plus, ShieldCheck } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import AdminPageHeader from "./components/AdminPageHeader";
import AdminModal from "./components/AdminModal";
import ConfirmModal from "./components/ConfirmModal";
import { vendors as seedVendors } from "./data";
import { useAdminToast } from "./AdminToastContext";
import { getAuthHeaders } from "../lib/authSession";

const API_BASE_URL = "http://localhost:8000/api";
const INITIAL_FORM = {
  name: "",
  email: "",
  phone_number: "",
  username: "",
  theatre: "",
  city: "",
  status: "Active",
  password: "",
};

export default function AdminVendors() {
  const { pushToast } = useAdminToast();
  const [showModal, setShowModal] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [activeVendor, setActiveVendor] = useState(null);
  const [editingVendor, setEditingVendor] = useState(null);
  const [vendorRows, setVendorRows] = useState(seedVendors);
  const [isSaving, setIsSaving] = useState(false);
  const [form, setForm] = useState(INITIAL_FORM);
  const [formError, setFormError] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("Status");
  const [cityFilter, setCityFilter] = useState("City");
  const [searchParams] = useSearchParams();
  const queryFromUrl = String(searchParams.get("q") || "");

  useEffect(() => {
    setSearchTerm(queryFromUrl);
  }, [queryFromUrl]);

  const cityOptions = useMemo(() => {
    const cities = Array.from(
      new Set(vendorRows.map((row) => String(row.city || "-").trim()).filter(Boolean))
    );
    return cities.sort((a, b) => a.localeCompare(b));
  }, [vendorRows]);

  const filteredVendorRows = useMemo(() => {
    let list = [...vendorRows];

    if (searchTerm.trim()) {
      const term = searchTerm.trim().toLowerCase();
      list = list.filter((vendor) => {
        const haystack = [vendor.name, vendor.email, vendor.theatre, vendor.city, vendor.status]
          .map((value) => String(value || "").toLowerCase())
          .join(" ");
        return haystack.includes(term);
      });
    }

    if (statusFilter !== "Status") {
      list = list.filter((vendor) => String(vendor.status || "") === statusFilter);
    }

    if (cityFilter !== "City") {
      list = list.filter((vendor) => String(vendor.city || "") === cityFilter);
    }

    return list;
  }, [vendorRows, searchTerm, statusFilter, cityFilter]);

  const formatDate = (value) => {
    if (!value) return "-";
    try {
      return new Date(value).toISOString().slice(0, 10);
    } catch (err) {
      return value;
    }
  };

  const normalizeVendor = (vendor) => ({
    id: vendor.id ?? vendor.email,
    name: vendor.name || "-",
    email: vendor.email || "-",
    theatre: vendor.theatre || "-",
    status: vendor.status || (vendor.is_active ? "Active" : "Blocked"),
    createdAt: formatDate(vendor.created_at),
    city: vendor.city || "-",
  });

  const loadVendors = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/admin/vendors/`, {
        headers: { Accept: "application/json", ...getAuthHeaders() },
      });
      if (!response.ok) return;
      const data = await response.json();
      if (Array.isArray(data?.vendors) && data.vendors.length) {
        setVendorRows(data.vendors.map(normalizeVendor));
      }
    } catch (err) {
      // keep fallback seed vendors
    }
  };

  useEffect(() => {
    loadVendors();
  }, []);

  const handleChange = (field) => (event) => {
    setForm((prev) => ({ ...prev, [field]: event.target.value }));
  };

  const handleSaveVendor = async () => {
    setFormError("");
    const isEditing = Boolean(editingVendor?.id);
    if (!form.name.trim() || !form.email.trim() || (!isEditing && !form.password)) {
      setFormError("Vendor name, email, and password are required.");
      return;
    }

    if (isEditing) {
      setVendorRows((rows) =>
        rows.map((vendor) =>
          vendor.id === editingVendor.id
            ? {
                ...vendor,
                name: form.name,
                email: form.email,
                theatre: form.theatre || "-",
                city: form.city || "-",
                status: form.status,
              }
            : vendor
        )
      );
      setShowModal(false);
      setEditingVendor(null);
      setForm(INITIAL_FORM);
      pushToast({
        title: "Vendor updated",
        message: `${form.name} has been updated.`,
      });
      return;
    }

    setIsSaving(true);
    try {
      const response = await fetch(`${API_BASE_URL}/admin/vendors/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify(form),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const message = data?.message || "Failed to create vendor.";
        throw new Error(message);
      }

      if (data?.vendor) {
        setVendorRows((rows) => [normalizeVendor(data.vendor), ...rows]);
      }

      setShowModal(false);
      setForm(INITIAL_FORM);
      setEditingVendor(null);
      pushToast({
        title: "Vendor added",
        message: "Vendor onboarding completed.",
      });
    } catch (err) {
      setFormError(err.message || "Failed to create vendor.");
      pushToast({
        title: "Vendor not added",
        message: err.message || "Failed to create vendor.",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const openEditVendor = (vendor) => {
    setEditingVendor(vendor);
    setForm(mapVendorToForm(vendor));
    setFormError("");
    setShowModal(true);
  };

  const handleConfirmBlockToggle = () => {
    if (!activeVendor?.id) return;
    const nextStatus = activeVendor.status === "Blocked" ? "Active" : "Blocked";
    setVendorRows((rows) =>
      rows.map((vendor) =>
        vendor.id === activeVendor.id ? { ...vendor, status: nextStatus } : vendor
      )
    );
    setShowConfirm(false);
    pushToast({
      title: "Vendor updated",
      message: `${activeVendor.name} is now ${nextStatus}.`,
    });
  };

  return (
    <>
      <AdminPageHeader
        title="Manage Vendors"
        subtitle="Admin controls vendor onboarding, access, and theatre assignments."
      >
        <button
          type="button"
          className="btn btn-primary admin-btn"
          onClick={() => {
            setForm(INITIAL_FORM);
            setEditingVendor(null);
            setFormError("");
            setShowModal(true);
          }}
        >
          <Plus size={16} className="me-2" />
          Add Vendor
        </button>
      </AdminPageHeader>

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div className="d-flex gap-2 flex-wrap admin-filter-row">
            <input
              className="form-control"
              placeholder="Search vendor"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
            />
            <select
              className="form-select"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option>Status</option>
              <option>Active</option>
              <option>Blocked</option>
              <option>Pending</option>
            </select>
            <select
              className="form-select"
              value={cityFilter}
              onChange={(event) => setCityFilter(event.target.value)}
            >
              <option>City</option>
              {cityOptions.map((city) => (
                <option key={city} value={city}>{city}</option>
              ))}
            </select>
          </div>
          <div className="text-muted small">{filteredVendorRows.length} vendors</div>
        </div>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Vendor</th>
                <th>Email</th>
                <th>Theatre</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredVendorRows.map((vendor) => (
                <tr key={vendor.id}>
                  <td>
                    <div className="fw-semibold">{vendor.name}</div>
                    <small className="text-muted">{vendor.city}</small>
                  </td>
                  <td>{vendor.email}</td>
                  <td>{vendor.theatre}</td>
                  <td>
                    <span
                      className={`badge-soft ${vendor.status === "Active" ? "success" : vendor.status === "Blocked" ? "danger" : "warning"}`}
                    >
                      {vendor.status}
                    </span>
                  </td>
                  <td>{vendor.createdAt}</td>
                  <td>
                    <div className="d-flex gap-2">
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => openEditVendor(vendor)}
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => {
                          setActiveVendor(vendor);
                          setShowConfirm(true);
                        }}
                      >
                        <Lock size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() =>
                          pushToast({
                            title: "Reset password",
                            message: `Reset link sent to ${vendor.email}.`,
                          })
                        }
                      >
                        <KeyRound size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() =>
                          pushToast({
                            title: "Access updated",
                            message: `Hall access updated for ${vendor.name}.`,
                          })
                        }
                      >
                        <ShieldCheck size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filteredVendorRows.length === 0 ? (
                <tr>
                  <td colSpan="6">No vendors found.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <nav className="d-flex justify-content-between align-items-center mt-3">
          <span className="text-muted small">Page 1 of 2</span>
          <ul className="pagination mb-0">
            <li className="page-item disabled"><span className="page-link">Prev</span></li>
            <li className="page-item active"><span className="page-link">1</span></li>
            <li className="page-item"><span className="page-link">2</span></li>
            <li className="page-item"><span className="page-link">Next</span></li>
          </ul>
        </nav>
      </section>

      <AdminModal
        show={showModal}
        title={editingVendor ? "Edit Vendor" : "Add Vendor"}
        onClose={() => {
          setShowModal(false);
          setEditingVendor(null);
        }}
        footer={
          <>
            <button
              type="button"
              className="btn btn-outline-light"
              onClick={() => {
                setShowModal(false);
                setEditingVendor(null);
              }}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSaveVendor}
              disabled={isSaving}
            >
              {isSaving ? "Saving..." : editingVendor ? "Update Vendor" : "Save Vendor"}
            </button>
          </>
        }
      >
        <div className="row g-3">
          <div className="col-md-6">
            <label className="form-label">Vendor name</label>
            <input
              className="form-control"
              placeholder="Vendor company"
              value={form.name}
              onChange={handleChange("name")}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Email</label>
            <input
              className="form-control"
              placeholder="vendor@email.com"
              value={form.email}
              onChange={handleChange("email")}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Phone number</label>
            <input
              className="form-control"
              placeholder="98XXXXXXXX"
              value={form.phone_number}
              onChange={handleChange("phone_number")}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Username</label>
            <input
              className="form-control"
              placeholder="vendor username"
              value={form.username}
              onChange={handleChange("username")}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Theatre name</label>
            <input
              className="form-control"
              placeholder="Theatre location"
              value={form.theatre}
              onChange={handleChange("theatre")}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">City</label>
            <input
              className="form-control"
              placeholder="Kathmandu"
              value={form.city}
              onChange={handleChange("city")}
            />
          </div>
          <div className="col-12">
            <label className="form-label">Status</label>
            <select className="form-select" value={form.status} onChange={handleChange("status")}>
              <option>Active</option>
              <option>Pending</option>
              <option>Blocked</option>
            </select>
          </div>
          <div className="col-12">
            <label className="form-label">Password</label>
            <input
              type="password"
              className="form-control"
              placeholder={editingVendor ? "Leave blank to keep existing password" : "Set vendor password"}
              value={form.password}
              onChange={handleChange("password")}
            />
          </div>
          {formError ? <div className="col-12 text-danger small">{formError}</div> : null}
        </div>
      </AdminModal>

      <ConfirmModal
        show={showConfirm}
        title={activeVendor?.status === "Blocked" ? "Unblock vendor?" : "Block vendor?"}
        description={
          activeVendor?.status === "Blocked"
            ? "Vendor access will be restored."
            : "Vendor access will be paused until unblocked by admin."
        }
        onCancel={() => setShowConfirm(false)}
        onConfirm={handleConfirmBlockToggle}
      />
    </>
  );
}

function mapVendorToForm(vendor) {
  return {
    name: vendor?.name || "",
    email: vendor?.email || "",
    phone_number: vendor?.phone_number || "",
    username: vendor?.username || "",
    theatre: vendor?.theatre || "",
    city: vendor?.city || "",
    status: vendor?.status || "Active",
    password: "",
  };
}
