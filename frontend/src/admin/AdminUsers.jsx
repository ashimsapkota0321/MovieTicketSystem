import { useEffect, useMemo, useState } from "react";
import { Eye, Pencil, Plus, ShieldAlert, Trash2 } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import AdminModal from "./components/AdminModal";
import ConfirmModal from "./components/ConfirmModal";
import { useAdminToast } from "./AdminToastContext";
import {
  createUserAdmin,
  deleteUserAdmin,
  fetchUsersAdmin,
  updateUserAdmin,
} from "../lib/catalogApi";

const INITIAL_FORM = {
  first_name: "",
  middle_name: "",
  last_name: "",
  email: "",
  phone_number: "",
  dob: "",
  username: "",
  password: "",
  status: "Active",
};

export default function AdminUsers() {
  const { pushToast } = useAdminToast();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [userToDelete, setUserToDelete] = useState(null);
  const [form, setForm] = useState(INITIAL_FORM);
  const [formError, setFormError] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [roleFilter, setRoleFilter] = useState("Role");
  const [statusFilter, setStatusFilter] = useState("Status");
  const [isSaving, setIsSaving] = useState(false);

  const formatDate = (value) => {
    if (!value) return "-";
    try {
      return new Date(value).toISOString().slice(0, 10);
    } catch {
      return value;
    }
  };

  const buildName = (user) => {
    const name = [user.first_name, user.middle_name, user.last_name]
      .filter(Boolean)
      .join(" ")
      .trim();
    return name || user.full_name || user.username || user.email || `User ${user.id}`;
  };

  const getStatusLabel = (user) => (user.is_active === false ? "Blocked" : "Active");

  const loadUsers = async () => {
    setLoading(true);
    try {
      const data = await fetchUsersAdmin();
      setUsers(Array.isArray(data) ? data : []);
    } catch (error) {
      pushToast({
        title: "Load failed",
        message: error.message || "Unable to load users.",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const filteredUsers = useMemo(() => {
    let list = [...users];
    if (searchTerm.trim()) {
      const term = searchTerm.trim().toLowerCase();
      list = list.filter((user) => {
        const name = buildName(user).toLowerCase();
        const email = String(user.email || "").toLowerCase();
        const phone = String(user.phone_number || "").toLowerCase();
        const username = String(user.username || "").toLowerCase();
        return (
          name.includes(term) ||
          email.includes(term) ||
          phone.includes(term) ||
          username.includes(term)
        );
      });
    }
    if (roleFilter !== "Role" && roleFilter !== "Customer") {
      list = [];
    }
    if (statusFilter !== "Status") {
      list = list.filter((user) => getStatusLabel(user) === statusFilter);
    }
    return list;
  }, [users, searchTerm, roleFilter, statusFilter]);

  const openAdd = () => {
    setEditingUser(null);
    setForm(INITIAL_FORM);
    setFormError("");
    setShowModal(true);
  };

  const openEdit = (user) => {
    setEditingUser(user);
    setForm(buildFormFromUser(user));
    setFormError("");
    setShowModal(true);
  };

  const handleSave = async () => {
    setFormError("");
    const isEditing = Boolean(editingUser?.id);

    if (!form.first_name.trim() || !form.last_name.trim() || !form.email.trim() || !form.phone_number.trim()) {
      setFormError("First name, last name, email, and phone number are required.");
      return;
    }

    if (!form.dob) {
      setFormError("Date of birth is required.");
      return;
    }

    if (!isEditing && !form.password) {
      setFormError("Password is required for new users.");
      return;
    }

    const payload = buildPayload(form, Boolean(form.password));

    setIsSaving(true);
    try {
      if (isEditing) {
        await updateUserAdmin(editingUser.id, payload, { method: "PUT" });
      } else {
        await createUserAdmin(payload);
      }
      await loadUsers();
      setShowModal(false);
      setForm(INITIAL_FORM);
      pushToast({
        title: "Saved",
        message: isEditing ? "User updated." : "User created.",
      });
    } catch (error) {
      setFormError(error.message || "Unable to save user.");
      pushToast({
        title: "Save failed",
        message: error.message || "Unable to save user.",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!userToDelete?.id) return;
    try {
      await deleteUserAdmin(userToDelete.id);
      await loadUsers();
      setShowConfirm(false);
      setUserToDelete(null);
      pushToast({ title: "Deleted", message: "User removed." });
    } catch (error) {
      pushToast({
        title: "Delete failed",
        message: error.message || "Unable to delete user.",
      });
    }
  };

  const handleToggleStatus = async (user) => {
    const currentActive = user.is_active !== false;
    const nextActive = !currentActive;
    try {
      await updateUserAdmin(user.id, { is_active: nextActive }, { method: "PATCH" });
      await loadUsers();
      pushToast({
        title: "User status updated",
        message: `${buildName(user)} is now ${nextActive ? "Active" : "Blocked"}.`,
      });
    } catch (error) {
      pushToast({
        title: "Update failed",
        message: error.message || "Unable to update user status.",
      });
    }
  };

  return (
    <>
      <AdminPageHeader
        title="Manage Users"
        subtitle="Monitor user registrations, roles, and account status."
      >
        <button type="button" className="btn btn-primary admin-btn" onClick={openAdd}>
          <Plus size={16} className="me-2" />
          Add User
        </button>
      </AdminPageHeader>

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div className="d-flex gap-2 flex-wrap">
            <input
              className="form-control"
              placeholder="Search user"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
            />
            <select
              className="form-select"
              value={roleFilter}
              onChange={(event) => setRoleFilter(event.target.value)}
            >
              <option>Role</option>
              <option>Customer</option>
              <option>Vendor</option>
              <option>Admin</option>
            </select>
            <select
              className="form-select"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option>Status</option>
              <option>Active</option>
              <option>Blocked</option>
            </select>
          </div>
          <div className="text-muted small">
            {loading ? "Loading..." : `${filteredUsers.length} users`}
          </div>
        </div>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Role</th>
                <th>Status</th>
                <th>Registered</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map((user) => (
                <tr key={user.id}>
                  <td>
                    <div className="fw-semibold">{buildName(user)}</div>
                    <small className="text-muted">{user.id}</small>
                  </td>
                  <td>{user.email || "-"}</td>
                  <td>{user.phone_number || "-"}</td>
                  <td>Customer</td>
                  <td>
                    <span
                      className={`badge-soft ${getStatusLabel(user) === "Active" ? "success" : "danger"}`}
                    >
                      {getStatusLabel(user)}
                    </span>
                  </td>
                  <td>{formatDate(user.date_joined)}</td>
                  <td>
                    <div className="d-flex gap-2">
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        title="View details"
                        onClick={() => openEdit(user)}
                      >
                        <Eye size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        title="Edit"
                        onClick={() => openEdit(user)}
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        title="Block/Unblock user"
                        onClick={() => handleToggleStatus(user)}
                      >
                        <ShieldAlert size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        title="Delete"
                        onClick={() => {
                          setUserToDelete(user);
                          setShowConfirm(true);
                        }}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan="7">No users found.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <AdminModal
        show={showModal}
        title={editingUser ? "Edit User" : "Add User"}
        onClose={() => setShowModal(false)}
        footer={
          <>
            <button type="button" className="btn btn-outline-light" onClick={() => setShowModal(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={handleSave} disabled={isSaving}>
              {isSaving ? "Saving..." : "Save"}
            </button>
          </>
        }
      >
        <div className="row g-3">
          <div className="col-md-4">
            <label className="form-label">First name</label>
            <input
              className="form-control"
              value={form.first_name}
              onChange={(event) => setForm((prev) => ({ ...prev, first_name: event.target.value }))}
            />
          </div>
          <div className="col-md-4">
            <label className="form-label">Middle name</label>
            <input
              className="form-control"
              value={form.middle_name}
              onChange={(event) => setForm((prev) => ({ ...prev, middle_name: event.target.value }))}
            />
          </div>
          <div className="col-md-4">
            <label className="form-label">Last name</label>
            <input
              className="form-control"
              value={form.last_name}
              onChange={(event) => setForm((prev) => ({ ...prev, last_name: event.target.value }))}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Email</label>
            <input
              className="form-control"
              value={form.email}
              onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Phone number</label>
            <input
              className="form-control"
              value={form.phone_number}
              onChange={(event) => setForm((prev) => ({ ...prev, phone_number: event.target.value }))}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Date of birth</label>
            <input
              type="date"
              className="form-control"
              value={form.dob}
              onChange={(event) => setForm((prev) => ({ ...prev, dob: event.target.value }))}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Username</label>
            <input
              className="form-control"
              value={form.username}
              onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Status</label>
            <select
              className="form-select"
              value={form.status}
              onChange={(event) => setForm((prev) => ({ ...prev, status: event.target.value }))}
            >
              <option>Active</option>
              <option>Blocked</option>
            </select>
          </div>
          <div className="col-md-6">
            <label className="form-label">Password</label>
            <input
              type="password"
              className="form-control"
              placeholder={editingUser ? "Leave blank to keep" : "Set user password"}
              value={form.password}
              onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
            />
          </div>
          {formError ? <div className="col-12 text-danger small">{formError}</div> : null}
        </div>
      </AdminModal>

      <ConfirmModal
        show={showConfirm}
        title="Delete user?"
        description="This action will permanently remove the user account."
        onCancel={() => setShowConfirm(false)}
        onConfirm={handleDelete}
      />
    </>
  );
}

function buildFormFromUser(user) {
  return {
    first_name: user.first_name || "",
    middle_name: user.middle_name || "",
    last_name: user.last_name || "",
    email: user.email || "",
    phone_number: user.phone_number || "",
    dob: user.dob || "",
    username: user.username || "",
    password: "",
    status: user.is_active === false ? "Blocked" : "Active",
  };
}

function buildPayload(form, includePassword) {
  const payload = {
    first_name: form.first_name.trim(),
    middle_name: form.middle_name.trim() || null,
    last_name: form.last_name.trim(),
    email: form.email.trim(),
    phone_number: form.phone_number.trim(),
    dob: form.dob || null,
    username: form.username.trim() || null,
    is_active: form.status === "Active",
  };
  if (includePassword && form.password) {
    payload.password = form.password;
  }
  return payload;
}
