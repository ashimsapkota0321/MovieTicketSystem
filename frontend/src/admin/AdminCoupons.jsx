import { useEffect, useMemo, useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import AdminModal from "./components/AdminModal";
import ConfirmModal from "./components/ConfirmModal";
import { useAdminToast } from "./AdminToastContext";
import {
  createAdminCoupon,
  deleteAdminCoupon,
  fetchAdminCoupons,
  updateAdminCoupon,
} from "../lib/catalogApi";

const EMPTY_FORM = {
  code: "",
  discount_type: "PERCENTAGE",
  discount_value: "",
  min_booking_amount: "",
  usage_limit: "",
  expiry_date: "",
  is_active: true,
};

export default function AdminCoupons() {
  const { pushToast } = useAdminToast();
  const [coupons, setCoupons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingCoupon, setEditingCoupon] = useState(null);
  const [showDelete, setShowDelete] = useState(false);
  const [couponToDelete, setCouponToDelete] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);

  const sortedCoupons = useMemo(
    () => [...coupons].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || ""))),
    [coupons]
  );

  const loadCoupons = async () => {
    setLoading(true);
    try {
      const list = await fetchAdminCoupons();
      setCoupons(Array.isArray(list) ? list : []);
    } catch (error) {
      pushToast({ title: "Load failed", message: error.message || "Unable to load coupons." });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCoupons();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const resetForm = () => {
    setEditingCoupon(null);
    setForm(EMPTY_FORM);
  };

  const openAdd = () => {
    resetForm();
    setShowModal(true);
  };

  const openEdit = (coupon) => {
    setEditingCoupon(coupon);
    setForm({
      code: coupon?.code || "",
      discount_type: coupon?.discount_type || "PERCENTAGE",
      discount_value: toInputNumber(coupon?.discount_value),
      min_booking_amount: toInputNumber(coupon?.min_booking_amount),
      usage_limit: coupon?.usage_limit != null ? String(coupon.usage_limit) : "",
      expiry_date: toInputDateTime(coupon?.expiry_date),
      is_active: Boolean(coupon?.is_active),
    });
    setShowModal(true);
  };

  const handleSave = async () => {
    const payload = {
      code: String(form.code || "").trim().toUpperCase(),
      discount_type: form.discount_type,
      discount_value: Number(form.discount_value || 0),
      min_booking_amount: Number(form.min_booking_amount || 0),
      usage_limit: form.usage_limit ? Number(form.usage_limit) : null,
      expiry_date: form.expiry_date || null,
      is_active: Boolean(form.is_active),
    };

    if (!payload.code) {
      pushToast({ title: "Invalid input", message: "Coupon code is required." });
      return;
    }
    if (payload.discount_value < 0) {
      pushToast({ title: "Invalid input", message: "Discount value must be non-negative." });
      return;
    }
    if (payload.discount_type === "PERCENTAGE" && payload.discount_value > 100) {
      pushToast({ title: "Invalid input", message: "Percentage discount cannot exceed 100." });
      return;
    }

    try {
      if (editingCoupon?.id) {
        await updateAdminCoupon(editingCoupon.id, payload);
      } else {
        await createAdminCoupon(payload);
      }
      setShowModal(false);
      resetForm();
      await loadCoupons();
      pushToast({
        title: "Saved",
        message: editingCoupon ? "Coupon updated successfully." : "Coupon created successfully.",
      });
    } catch (error) {
      pushToast({ title: "Save failed", message: error.message || "Unable to save coupon." });
    }
  };

  const handleDelete = async () => {
    if (!couponToDelete?.id) return;
    try {
      await deleteAdminCoupon(couponToDelete.id);
      setShowDelete(false);
      setCouponToDelete(null);
      await loadCoupons();
      pushToast({ title: "Deleted", message: "Coupon deleted successfully." });
    } catch (error) {
      pushToast({ title: "Delete failed", message: error.message || "Unable to delete coupon." });
    }
  };

  return (
    <>
      <AdminPageHeader
        title="Manage Coupons"
        subtitle="Create and control promotion codes for ticket discounts."
      >
        <button type="button" className="btn btn-primary admin-btn" onClick={openAdd}>
          <Plus size={16} className="me-2" />
          Add Coupon
        </button>
      </AdminPageHeader>

      <section className="admin-card">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <div className="text-muted small">Showing {sortedCoupons.length} coupons</div>
        </div>

        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Type</th>
                <th>Value</th>
                <th>Minimum</th>
                <th>Usage</th>
                <th>Expiry</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedCoupons.map((coupon) => (
                <tr key={coupon.id}>
                  <td className="fw-semibold">{coupon.code}</td>
                  <td>{coupon.discount_type === "PERCENTAGE" ? "Percentage" : "Fixed"}</td>
                  <td>
                    {coupon.discount_type === "PERCENTAGE"
                      ? `${coupon.discount_value}%`
                      : `NPR ${coupon.discount_value}`}
                  </td>
                  <td>NPR {coupon.min_booking_amount || 0}</td>
                  <td>
                    {coupon.usage_count || 0}
                    {coupon.usage_limit ? ` / ${coupon.usage_limit}` : " / Unlimited"}
                  </td>
                  <td>{formatDateTime(coupon.expiry_date)}</td>
                  <td>
                    <span className={`badge ${coupon.is_active ? "text-bg-success" : "text-bg-secondary"}`}>
                      {coupon.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td>
                    <div className="d-flex gap-2">
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => openEdit(coupon)}
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => {
                          setCouponToDelete(coupon);
                          setShowDelete(true);
                        }}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && sortedCoupons.length === 0 ? (
                <tr>
                  <td colSpan="8">No coupons created yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <AdminModal
        show={showModal}
        title={editingCoupon ? "Edit Coupon" : "Add Coupon"}
        onClose={() => {
          setShowModal(false);
          resetForm();
        }}
        footer={
          <>
            <button
              type="button"
              className="btn btn-outline-light"
              onClick={() => {
                setShowModal(false);
                resetForm();
              }}
            >
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={handleSave}>
              Save Coupon
            </button>
          </>
        }
      >
        <div className="row g-3">
          <div className="col-md-6">
            <label className="form-label">Coupon code</label>
            <input
              className="form-control"
              value={form.code}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, code: event.target.value.toUpperCase() }))
              }
              placeholder="NEWUSER20"
            />
          </div>

          <div className="col-md-6">
            <label className="form-label">Discount type</label>
            <select
              className="form-select"
              value={form.discount_type}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, discount_type: event.target.value }))
              }
            >
              <option value="PERCENTAGE">Percentage</option>
              <option value="FIXED">Fixed</option>
            </select>
          </div>

          <div className="col-md-6">
            <label className="form-label">Discount value</label>
            <input
              type="number"
              min="0"
              className="form-control"
              value={form.discount_value}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, discount_value: event.target.value }))
              }
              placeholder={form.discount_type === "PERCENTAGE" ? "10" : "100"}
            />
          </div>

          <div className="col-md-6">
            <label className="form-label">Minimum booking amount</label>
            <input
              type="number"
              min="0"
              className="form-control"
              value={form.min_booking_amount}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, min_booking_amount: event.target.value }))
              }
              placeholder="0"
            />
          </div>

          <div className="col-md-6">
            <label className="form-label">Usage limit</label>
            <input
              type="number"
              min="1"
              className="form-control"
              value={form.usage_limit}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, usage_limit: event.target.value }))
              }
              placeholder="Leave empty for unlimited"
            />
          </div>

          <div className="col-md-6">
            <label className="form-label">Expiry date</label>
            <input
              type="datetime-local"
              className="form-control"
              value={form.expiry_date}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, expiry_date: event.target.value }))
              }
            />
          </div>

          <div className="col-12">
            <label className="form-check d-inline-flex gap-2 align-items-center">
              <input
                type="checkbox"
                className="form-check-input"
                checked={form.is_active}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, is_active: event.target.checked }))
                }
              />
              <span className="form-check-label">Coupon is active</span>
            </label>
          </div>
        </div>
      </AdminModal>

      <ConfirmModal
        show={showDelete}
        title="Delete Coupon"
        message={`Delete coupon ${couponToDelete?.code || ""}?`}
        confirmText="Delete"
        cancelText="Cancel"
        onCancel={() => {
          setShowDelete(false);
          setCouponToDelete(null);
        }}
        onConfirm={handleDelete}
      />
    </>
  );
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString();
}

function toInputNumber(value) {
  if (value === null || value === undefined) return "";
  const num = Number(value);
  if (Number.isNaN(num)) return "";
  return String(num);
}

function toInputDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hour = String(date.getHours()).padStart(2, "0");
  const minute = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hour}:${minute}`;
}
