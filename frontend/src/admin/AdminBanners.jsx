import { useEffect, useMemo, useState } from "react";
import { Eye, Pencil, Plus, Trash2 } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import AdminModal from "./components/AdminModal";
import ConfirmModal from "./components/ConfirmModal";
import { useAdminToast } from "./AdminToastContext";
import {
  createBanner,
  deleteBanner,
  fetchAdminBanners,
  fetchMovies,
  updateBanner,
} from "../lib/catalogApi";

const BANNER_TYPES = [
  { value: "MOVIE", label: "Movie Banner" },
  { value: "PROMO", label: "Promo Banner" },
];

export default function AdminBanners() {
  const { pushToast } = useAdminToast();
  const [banners, setBanners] = useState([]);
  const [movies, setMovies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingBanner, setEditingBanner] = useState(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [bannerToDelete, setBannerToDelete] = useState(null);
  const [form, setForm] = useState(() => buildEmptyBanner());
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState("");

  const movieLookup = useMemo(() => {
    const map = new Map();
    movies.forEach((movie) => map.set(String(movie.id), movie));
    return map;
  }, [movies]);

  const loadBanners = async () => {
    setLoading(true);
    try {
      const list = await fetchAdminBanners();
      setBanners(Array.isArray(list) ? list : []);
    } catch (error) {
      pushToast({
        title: "Load failed",
        message: error.message || "Unable to load banners.",
      });
    } finally {
      setLoading(false);
    }
  };

  const loadMovies = async () => {
    try {
      const list = await fetchMovies();
      setMovies(Array.isArray(list) ? list : []);
    } catch (error) {
      pushToast({
        title: "Movies unavailable",
        message: error.message || "Unable to load movies for banners.",
      });
    }
  };

  useEffect(() => {
    loadBanners();
    loadMovies();
    return () => {
      revokeIfBlob(imagePreview);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const resetForm = () => {
    revokeIfBlob(imagePreview);
    setForm(buildEmptyBanner());
    setImageFile(null);
    setImagePreview("");
  };

  const openAdd = () => {
    setEditingBanner(null);
    resetForm();
    setShowModal(true);
  };

  const openEdit = (banner) => {
    setEditingBanner(banner);
    setForm(mapBannerToForm(banner));
    setImageFile(null);
    setImagePreview(banner?.image || "");
    setShowModal(true);
  };

  const handleImageChange = (file) => {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      pushToast({ title: "Invalid file", message: "Please select an image file." });
      return;
    }
    setImageFile(file);
    revokeIfBlob(imagePreview);
    setImagePreview(URL.createObjectURL(file));
  };

  const handleSave = async () => {
    if (form.banner_type === "MOVIE" && !form.movie_id) {
      pushToast({
        title: "Movie required",
        message: "Please select a movie for a movie banner.",
      });
      return;
    }
    const hasImage = Boolean(imageFile || imagePreview);
    if (!hasImage) {
      pushToast({
        title: "Image required",
        message: "Please upload a banner image.",
      });
      return;
    }
    const payload = buildFormData(form, imageFile);

    try {
      if (editingBanner?.id) {
        await updateBanner(editingBanner.id, payload, { method: "PATCH" });
      } else {
        await createBanner(payload);
      }
      await loadBanners();
      setShowModal(false);
      resetForm();
      pushToast({
        title: "Banner saved",
        message: editingBanner ? "Banner updated successfully." : "Banner created.",
      });
    } catch (error) {
      pushToast({
        title: "Save failed",
        message: error.message || "Unable to save banner.",
      });
    }
  };

  const handleDelete = async () => {
    if (!bannerToDelete?.id) return;
    try {
      await deleteBanner(bannerToDelete.id);
      await loadBanners();
      setShowConfirm(false);
      pushToast({ title: "Banner deleted", message: "Banner removed successfully." });
    } catch (error) {
      pushToast({
        title: "Delete failed",
        message: error.message || "Unable to delete banner.",
      });
    }
  };

  const handleToggleActive = async (banner) => {
    const payload = new FormData();
    payload.append("is_active", banner.is_active ? "false" : "true");
    try {
      await updateBanner(banner.id, payload, { method: "PATCH" });
      await loadBanners();
    } catch (error) {
      pushToast({
        title: "Update failed",
        message: error.message || "Unable to update status.",
      });
    }
  };

  return (
    <>
      <AdminPageHeader
        title="Manage Banners"
        subtitle="Control hero banners shown on Home and Movies pages."
      >
        <button type="button" className="btn btn-primary admin-btn" onClick={openAdd}>
          <Plus size={16} className="me-2" />
          Add Banner
        </button>
      </AdminPageHeader>

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div className="text-muted small">Showing {banners.length} banners</div>
        </div>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Image</th>
                <th>Type</th>
                <th>Movie</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {banners.map((banner) => (
                <tr key={banner.id}>
                  <td>
                    {banner.image ? (
                      <img
                        className="admin-banner-thumb"
                        src={banner.image}
                        alt={banner.banner_type}
                      />
                    ) : (
                      "-"
                    )}
                  </td>
                  <td>
                    <span className="fw-semibold">
                      {banner.banner_type === "MOVIE" ? "Movie" : "Promo"}
                    </span>
                  </td>
                  <td>
                    {banner.banner_type === "MOVIE" ? (
                      <span>{banner.movie?.title || "-"}</span>
                    ) : (
                      <span className="text-muted small">
                        Promo banner
                      </span>
                    )}
                  </td>
                  <td>
                    <button
                      type="button"
                      className={`btn btn-sm ${
                        banner.is_active ? "btn-outline-light" : "btn-danger"
                      }`}
                      onClick={() => handleToggleActive(banner)}
                    >
                      {banner.is_active ? "Active" : "Inactive"}
                    </button>
                  </td>
                  <td>
                    <div className="d-flex gap-2">
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => openEdit(banner)}
                      >
                        <Eye size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => openEdit(banner)}
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => {
                          setBannerToDelete(banner);
                          setShowConfirm(true);
                        }}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && banners.length === 0 ? (
                <tr>
                  <td colSpan="5">No banners added yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <AdminModal
        show={showModal}
        title={editingBanner ? "Edit Banner" : "Add Banner"}
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
              Save Banner
            </button>
          </>
        }
      >
        <div className="row g-3">
          <div className="col-12">
            <label className="form-label">Banner type</label>
            <div className="d-flex flex-wrap gap-2">
              {BANNER_TYPES.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`btn ${
                    form.banner_type === option.value ? "btn-primary" : "btn-outline-light"
                  }`}
                  onClick={() =>
                    setForm((prev) => ({
                      ...prev,
                      banner_type: option.value,
                      movie_id: option.value === "MOVIE" ? prev.movie_id : "",
                    }))
                  }
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {form.banner_type === "MOVIE" ? (
            <div className="col-12">
              <label className="form-label">Select movie</label>
              <select
                className="form-select"
                value={form.movie_id}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, movie_id: event.target.value }))
                }
              >
                <option value="">Select a movie</option>
                {movies.map((movie) => (
                  <option key={movie.id} value={movie.id}>
                    {movie.title}
                  </option>
                ))}
              </select>
              {form.movie_id ? (
                <small className="text-muted d-block mt-1">
                  Using movie details from "{movieLookup.get(String(form.movie_id))?.title}".
                </small>
              ) : null}
            </div>
          ) : null}

          <div className="col-md-6">
            <label className="form-label">Banner image</label>
            <input
              type="file"
              className="form-control"
              accept="image/*"
              onChange={(event) => handleImageChange(event.target.files?.[0])}
            />
            {imagePreview ? (
              <img className="admin-banner-preview" src={imagePreview} alt="Banner" />
            ) : null}
          </div>

          <div className="col-md-6">
            <label className="form-label">Status</label>
            <select
              className="form-select"
              value={form.is_active ? "true" : "false"}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, is_active: event.target.value === "true" }))
              }
            >
              <option value="true">Active</option>
              <option value="false">Inactive</option>
            </select>
          </div>
        </div>
      </AdminModal>

      <ConfirmModal
        show={showConfirm}
        title="Delete banner?"
        description="This action will remove the banner permanently."
        onCancel={() => setShowConfirm(false)}
        onConfirm={handleDelete}
      />
    </>
  );
}

function buildEmptyBanner() {
  return {
    banner_type: "MOVIE",
    movie_id: "",
    is_active: true,
  };
}

function mapBannerToForm(banner) {
  return {
    banner_type: banner?.banner_type || "MOVIE",
    movie_id: banner?.movie?.id ? String(banner.movie.id) : "",
    is_active: banner?.is_active ?? true,
  };
}

function buildFormData(form, imageFile) {
  const payload = new FormData();
  payload.append("banner_type", form.banner_type);
  if (form.banner_type === "MOVIE" && form.movie_id) {
    payload.append("movie", form.movie_id);
  }
  if (imageFile) payload.append("image", imageFile);
  payload.append("is_active", form.is_active ? "true" : "false");
  return payload;
}

function revokeIfBlob(url) {
  if (!url) return;
  if (url.startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
}
