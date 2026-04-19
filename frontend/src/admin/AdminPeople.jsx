import { useEffect, useMemo, useState } from "react";
import { Eye, Pencil, Plus, Trash2 } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import AdminPageHeader from "./components/AdminPageHeader";
import AdminModal from "./components/AdminModal";
import ConfirmModal from "./components/ConfirmModal";
import { useAdminToast } from "./AdminToastContext";
import {
  createPerson,
  deletePerson,
  fetchPeople,
  updatePerson,
} from "../lib/catalogApi";

export default function AdminPeople() {
  const { pushToast } = useAdminToast();
  const [searchParams] = useSearchParams();
  const selectedId = searchParams.get("personId");

  const [people, setPeople] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editingPerson, setEditingPerson] = useState(null);
  const [isReadOnlyMode, setIsReadOnlyMode] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [personToDelete, setPersonToDelete] = useState(null);
  const [form, setForm] = useState(buildEmptyPerson());
  const [searchTerm, setSearchTerm] = useState("");

  const loadPeople = async () => {
    setLoading(true);
    try {
      const data = await fetchPeople();
      setPeople(Array.isArray(data) ? data : []);
    } catch (error) {
      pushToast({
        title: "Load failed",
        message: error.message || "Unable to load people list.",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPeople();
  }, []);

  useEffect(() => {
    if (!selectedId || !people.length) return;
    const match = people.find((person) => String(person.id) === String(selectedId));
    if (match) {
      openEdit(match);
    }
  }, [selectedId, people]);

  const filteredPeople = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return people;

    return people.filter((person) => {
      const haystack = [
        person.full_name || person.fullName,
        person.nationality,
        person.slug,
        person.instagram,
        person.imdb,
        person.facebook,
      ]
        .map((value) => String(value || "").toLowerCase())
        .join(" ");
      return haystack.includes(term);
    });
  }, [people, searchTerm]);

  const openAdd = () => {
    setEditingPerson(null);
    setIsReadOnlyMode(false);
    setForm(buildEmptyPerson());
    setShowModal(true);
  };

  const openEdit = (person, { readOnly = false } = {}) => {
    setEditingPerson(person);
    setIsReadOnlyMode(Boolean(readOnly));
    setForm(buildFormFromPerson(person));
    setShowModal(true);
  };

  const handleSave = async () => {
    if (isReadOnlyMode) {
      return;
    }
    if (!form.full_name.trim()) {
      pushToast({ title: "Missing name", message: "Please enter a full name." });
      return;
    }
    const payload = buildPayload(form);
    try {
      if (editingPerson?.id) {
        await updatePerson(editingPerson.id, payload);
      } else {
        await createPerson(payload);
      }
      await loadPeople();
      setShowModal(false);
      pushToast({
        title: "Saved",
        message: editingPerson ? "Person details updated." : "Person added.",
      });
    } catch (error) {
      pushToast({
        title: "Save failed",
        message: error.message || "Unable to save person.",
      });
    }
  };

  const handleDelete = async () => {
    if (!personToDelete?.id) return;
    try {
      await deletePerson(personToDelete.id);
      await loadPeople();
      setShowConfirm(false);
      pushToast({ title: "Deleted", message: "Person removed." });
    } catch (error) {
      pushToast({
        title: "Delete failed",
        message: error.message || "Unable to delete person.",
      });
    }
  };

  return (
    <>
      <AdminPageHeader
        title="Manage Cast & Crew"
        subtitle="Add or update cast/crew profiles used across movies."
      >
        <button type="button" className="btn btn-primary admin-btn" onClick={openAdd}>
          <Plus size={16} className="me-2" />
          Add Person
        </button>
      </AdminPageHeader>

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div className="d-flex gap-2 flex-wrap admin-filter-row">
            <input
              className="form-control"
              placeholder="Search person"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
            />
          </div>
          <div className="text-muted small">
            {loading ? "Loading..." : `${filteredPeople.length} people`}
          </div>
        </div>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Nationality</th>
                <th>Instagram</th>
                <th>IMDb</th>
                <th>Facebook</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredPeople.map((person) => (
                <tr key={person.id}>
                  <td>{person.id}</td>
                  <td>
                    <div className="fw-semibold">{person.full_name || person.fullName}</div>
                    <small className="text-muted">{person.slug || "-"}</small>
                  </td>
                  <td>{person.nationality || "-"}</td>
                  <td>{person.instagram ? "Yes" : "-"}</td>
                  <td>{person.imdb ? "Yes" : "-"}</td>
                  <td>{person.facebook ? "Yes" : "-"}</td>
                  <td>
                    <div className="d-flex gap-2">
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        title="View details"
                        onClick={() => openEdit(person, { readOnly: true })}
                      >
                        <Eye size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        title="Edit"
                        onClick={() => openEdit(person)}
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        title="Delete"
                        onClick={() => {
                          setPersonToDelete(person);
                          setShowConfirm(true);
                        }}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {filteredPeople.length === 0 ? (
                <tr>
                  <td colSpan="7">No people added yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <AdminModal
        show={showModal}
        title={editingPerson ? (isReadOnlyMode ? "View Person" : "Edit Person") : "Add Person"}
        onClose={() => {
          setShowModal(false);
          setIsReadOnlyMode(false);
        }}
        footer={
          <>
            <button
              type="button"
              className="btn btn-outline-light"
              onClick={() => {
                setShowModal(false);
                setIsReadOnlyMode(false);
              }}
            >
              {isReadOnlyMode ? "Close" : "Cancel"}
            </button>
            {!isReadOnlyMode ? (
              <button type="button" className="btn btn-primary" onClick={handleSave}>
                Save
              </button>
            ) : null}
          </>
        }
      >
        {isReadOnlyMode ? (
          <div className="admin-details-view">
            <div className="admin-details-row">
              <div className="admin-details-label">Full Name</div>
              <div className="admin-details-value">{form.full_name || "-"}</div>
            </div>
            <div className="admin-details-row">
              <div className="admin-details-label">Nationality</div>
              <div className="admin-details-value">{form.nationality || "-"}</div>
            </div>
            <div className="admin-details-row">
              <div className="admin-details-label">Date of Birth</div>
              <div className="admin-details-value">{form.date_of_birth || "-"}</div>
            </div>
            <div className="admin-details-row">
              <div className="admin-details-label">Photo</div>
              <div className="admin-details-value">
                {form.photo_url ? <img className="admin-details-image" src={form.photo_url} alt={form.full_name || "Person"} /> : "-"}
              </div>
            </div>
            <div className="admin-details-row">
              <div className="admin-details-label">Bio</div>
              <div className="admin-details-value">{form.bio || "-"}</div>
            </div>
            <div className="admin-details-row">
              <div className="admin-details-label">Instagram</div>
              <div className="admin-details-value">{form.instagram || "-"}</div>
            </div>
            <div className="admin-details-row">
              <div className="admin-details-label">IMDb</div>
              <div className="admin-details-value">{form.imdb || "-"}</div>
            </div>
            <div className="admin-details-row">
              <div className="admin-details-label">Facebook</div>
              <div className="admin-details-value">{form.facebook || "-"}</div>
            </div>
          </div>
        ) : (
          <fieldset disabled={isReadOnlyMode}>
          <div className="row g-3">
            <div className="col-md-6">
              <label className="form-label">Full name</label>
              <input
                className="form-control"
                value={form.full_name}
                onChange={(event) => setForm((prev) => ({ ...prev, full_name: event.target.value }))}
              />
            </div>
            <div className="col-md-6">
              <label className="form-label">Nationality</label>
              <input
                className="form-control"
                value={form.nationality}
                onChange={(event) => setForm((prev) => ({ ...prev, nationality: event.target.value }))}
              />
            </div>
            <div className="col-md-6">
              <label className="form-label">Date of birth</label>
              <input
                type="date"
                className="form-control"
                value={form.date_of_birth}
                onChange={(event) => setForm((prev) => ({ ...prev, date_of_birth: event.target.value }))}
              />
            </div>
            <div className="col-md-6">
              <label className="form-label">Photo URL</label>
              <input
                className="form-control"
                value={form.photo_url}
                onChange={(event) => setForm((prev) => ({ ...prev, photo_url: event.target.value }))}
              />
            </div>
            <div className="col-12">
              <label className="form-label">Bio</label>
              <textarea
                className="form-control"
                rows="3"
                value={form.bio}
                onChange={(event) => setForm((prev) => ({ ...prev, bio: event.target.value }))}
              />
            </div>
            <div className="col-md-4">
              <label className="form-label">Instagram</label>
              <input
                className="form-control"
                value={form.instagram}
                onChange={(event) => setForm((prev) => ({ ...prev, instagram: event.target.value }))}
              />
            </div>
            <div className="col-md-4">
              <label className="form-label">IMDb</label>
              <input
                className="form-control"
                value={form.imdb}
                onChange={(event) => setForm((prev) => ({ ...prev, imdb: event.target.value }))}
              />
            </div>
            <div className="col-md-4">
              <label className="form-label">Facebook</label>
              <input
                className="form-control"
                value={form.facebook}
                onChange={(event) => setForm((prev) => ({ ...prev, facebook: event.target.value }))}
              />
            </div>
          </div>
          </fieldset>
        )}
      </AdminModal>

      <ConfirmModal
        show={showConfirm}
        title="Delete person?"
        description="This action will remove the person profile but keep movie credits."
        onCancel={() => setShowConfirm(false)}
        onConfirm={handleDelete}
      />
    </>
  );
}

function buildEmptyPerson() {
  return {
    full_name: "",
    photo_url: "",
    bio: "",
    date_of_birth: "",
    nationality: "",
    instagram: "",
    imdb: "",
    facebook: "",
  };
}

function buildFormFromPerson(person) {
  return {
    full_name: person.full_name || person.fullName || "",
    photo_url: person.photo_url || person.photoUrl || "",
    bio: person.bio || "",
    date_of_birth: person.date_of_birth || person.dateOfBirth || "",
    nationality: person.nationality || "",
    instagram: person.instagram || "",
    imdb: person.imdb || "",
    facebook: person.facebook || "",
  };
}

function buildPayload(form) {
  return {
    full_name: form.full_name.trim(),
    photo_url: form.photo_url?.trim() || "",
    bio: form.bio || "",
    date_of_birth: form.date_of_birth || null,
    nationality: form.nationality || "",
    instagram: form.instagram || "",
    imdb: form.imdb || "",
    facebook: form.facebook || "",
  };
}
