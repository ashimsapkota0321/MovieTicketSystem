import { useEffect, useMemo, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import AdminModal from "../admin/components/AdminModal";
import ConfirmModal from "../admin/components/ConfirmModal";
import {
  createVendorFoodItem,
  deleteVendorFoodItem,
  fetchVendorFoodItems,
  updateVendorFoodItem,
} from "../lib/catalogApi";

export default function VendorFoodItems() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [form, setForm] = useState(() => buildEmptyForm());

  const availableCount = useMemo(
    () => items.filter((item) => item.isAvailable).length,
    [items]
  );
  const soldOutCount = useMemo(
    () => items.filter((item) => item.soldOut).length,
    [items]
  );

  const loadItems = async () => {
    setLoading(true);
    try {
      const data = await fetchVendorFoodItems();
      setItems(Array.isArray(data) ? data : []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadItems();
  }, []);

  const openCreate = () => {
    setEditing(null);
    setForm(buildEmptyForm());
    setModalOpen(true);
  };

  const openEdit = (item) => {
    setEditing(item);
    setForm({
      item_name: item?.itemName || "",
      category: item?.category || "",
      hall: item?.hall || "",
      price: String(item?.price || ""),
      track_inventory: Boolean(item?.trackInventory),
      stock_quantity: String(item?.stockQuantity ?? "0"),
      sold_out_threshold: String(item?.soldOutThreshold ?? "0"),
      is_available: Boolean(item?.isAvailable),
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    const payload = {
      item_name: form.item_name.trim(),
      category: form.category.trim(),
      hall: form.hall.trim(),
      price: Number(form.price || 0),
      track_inventory: form.track_inventory,
      stock_quantity: Number(form.stock_quantity || 0),
      sold_out_threshold: Number(form.sold_out_threshold || 0),
      is_available: form.is_available,
    };
    if (!payload.item_name || payload.price <= 0) return;
    if (payload.stock_quantity < 0 || payload.sold_out_threshold < 0) return;

    try {
      if (editing?.id) {
        await updateVendorFoodItem(editing.id, payload);
      } else {
        await createVendorFoodItem(payload);
      }
      setModalOpen(false);
      await loadItems();
    } catch {
      // keep modal open for correction
    }
  };

  const handleDelete = async () => {
    if (!deleting?.id) return;
    try {
      await deleteVendorFoodItem(deleting.id);
      setConfirmOpen(false);
      setDeleting(null);
      await loadItems();
    } catch {
      // noop
    }
  };

  return (
    <div className="vendor-dashboard">
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3">
        <div>
          <h2 className="mb-1">Food Item Management</h2>
          <p className="text-muted mb-0">
            Add food items by hall. Users will only see food page if items exist for that cinema.
          </p>
        </div>
      </div>

      <section className="vendor-card mt-3">
        <div className="vendor-card-header">
          <div>
            <h3>Food Inventory</h3>
            <p>
              Total Items: {items.length} | Available: {availableCount} | Sold Out: {soldOutCount}
            </p>
          </div>
          <button type="button" className="vendor-chip" onClick={openCreate}>
            <Plus size={16} />
            Add Food Item
          </button>
        </div>

        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Category</th>
                <th>Hall</th>
                <th>Price</th>
                <th>Stock</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td className="fw-semibold">{item.itemName}</td>
                  <td>{item.category || "-"}</td>
                  <td>{item.hall || "All Halls"}</td>
                  <td>Rs {item.price}</td>
                  <td>
                    {item.trackInventory ? `${item.stockQuantity ?? 0} left` : "Not tracked"}
                  </td>
                  <td>
                    {item.soldOut
                      ? "Sold Out"
                      : item.isAvailable
                        ? "Available"
                        : "Disabled"}
                  </td>
                  <td>
                    <div className="d-flex gap-2">
                      <button type="button" className="vendor-chip" onClick={() => openEdit(item)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="vendor-icon-btn"
                        onClick={() => {
                          setDeleting(item);
                          setConfirmOpen(true);
                        }}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && items.length === 0 ? (
                <tr>
                  <td colSpan="7">No food items added yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <AdminModal
        show={modalOpen}
        title={editing ? "Edit Food Item" : "Add Food Item"}
        onClose={() => setModalOpen(false)}
        footer={
          <>
            <button type="button" className="btn btn-outline-light" onClick={() => setModalOpen(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={handleSave}>
              Save
            </button>
          </>
        }
      >
        <div className="row g-3">
          <div className="col-md-6">
            <label className="form-label">Item Name</label>
            <input
              className="form-control"
              value={form.item_name}
              onChange={(event) => setForm((prev) => ({ ...prev, item_name: event.target.value }))}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Category</label>
            <input
              className="form-control"
              placeholder="Popcorn, Beverages"
              value={form.category}
              onChange={(event) => setForm((prev) => ({ ...prev, category: event.target.value }))}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Hall</label>
            <input
              className="form-control"
              placeholder="Hall A (optional)"
              value={form.hall}
              onChange={(event) => setForm((prev) => ({ ...prev, hall: event.target.value }))}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Price</label>
            <input
              type="number"
              min="1"
              className="form-control"
              value={form.price}
              onChange={(event) => setForm((prev) => ({ ...prev, price: event.target.value }))}
            />
          </div>
          <div className="col-md-6">
            <label className="form-check">
              <input
                className="form-check-input"
                type="checkbox"
                checked={form.track_inventory}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, track_inventory: event.target.checked }))
                }
              />
              <span className="form-check-label">Track inventory stock</span>
            </label>
          </div>
          <div className="col-md-6">
            <label className="form-label">Stock Quantity</label>
            <input
              type="number"
              min="0"
              className="form-control"
              value={form.stock_quantity}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, stock_quantity: event.target.value }))
              }
              disabled={!form.track_inventory}
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Sold Out Threshold</label>
            <input
              type="number"
              min="0"
              className="form-control"
              value={form.sold_out_threshold}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, sold_out_threshold: event.target.value }))
              }
              disabled={!form.track_inventory}
            />
            <small className="text-muted">
              Item auto-marks sold out when stock is less than or equal to this value.
            </small>
          </div>
          <div className="col-12">
            <label className="form-check">
              <input
                className="form-check-input"
                type="checkbox"
                checked={form.is_available}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, is_available: event.target.checked }))
                }
              />
              <span className="form-check-label">Available for booking</span>
            </label>
          </div>
        </div>
      </AdminModal>

      <ConfirmModal
        show={confirmOpen}
        title="Delete Food Item"
        body={`Delete ${deleting?.itemName || "this item"}?`}
        onClose={() => setConfirmOpen(false)}
        onConfirm={handleDelete}
        confirmText="Delete"
        confirmVariant="danger"
      />
    </div>
  );
}

function buildEmptyForm() {
  return {
    item_name: "",
    category: "",
    hall: "",
    price: "",
    track_inventory: false,
    stock_quantity: "0",
    sold_out_threshold: "0",
    is_available: true,
  };
}
