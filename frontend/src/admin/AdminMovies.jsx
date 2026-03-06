import { useState } from "react";
import { Eye, Pencil, Plus, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import AdminPageHeader from "./components/AdminPageHeader";
import AdminModal from "./components/AdminModal";
import ConfirmModal from "./components/ConfirmModal";
import MovieForm from "./components/MovieForm";
import { useAdminToast } from "./AdminToastContext";
import { createMovie, deleteMovie, fetchMovieById, updateMovie } from "../lib/catalogApi";
import { useAppContext } from "../context/Appcontext";

export default function AdminMovies() {
  const { pushToast } = useAdminToast();
  const ctx = safeUseAppContext();
  const movies = ctx?.movies ?? [];
  const refreshCatalog = ctx?.refreshCatalog ?? (async () => {});
  const navigate = useNavigate();

  const [showModal, setShowModal] = useState(false);
  const [editingMovie, setEditingMovie] = useState(null);
  const [showConfirm, setShowConfirm] = useState(false);
  const [movieToDelete, setMovieToDelete] = useState(null);
  const [form, setForm] = useState(() => buildEmptyMovie());
  const [formLoading, setFormLoading] = useState(false);


  const openAdd = () => {
    setEditingMovie(null);
    setForm(buildEmptyMovie());
    setFormLoading(false);
    setShowModal(true);
  };

  const openEdit = async (movie) => {
    setEditingMovie(movie);
    setForm(buildEmptyMovie());
    setShowModal(true);
    if (!movie?.id) return;
    setFormLoading(true);
    try {
      const detail = await fetchMovieById(movie.id);
      setForm(buildFormFromMovie(detail));
    } catch (error) {
      pushToast({
        title: "Load failed",
        message: error.message || "Unable to load movie details.",
      });
    } finally {
      setFormLoading(false);
    }
  };

  const handleSave = async () => {
    if (!form.title.trim()) {
      pushToast({ title: "Missing title", message: "Please enter a movie title." });
      return;
    }
    const creditError = validateCredits(form);
    if (creditError) {
      pushToast({ title: "Cast/Crew issue", message: creditError });
      return;
    }

    const payload = {
      title: form.title.trim(),
      duration: form.duration.trim(),
      genre: form.genre.trim(),
      language: form.language.trim(),
      rating: form.rating.trim(),
      releaseDate: form.releaseDate,
      status: form.status || "COMING_SOON",
      synopsis: form.synopsis?.trim() || "",
      posterUrl: form.posterUrl?.trim() || "",
      trailerUrl: form.trailerUrl?.trim() || "",
    };
    payload.credits = buildCreditsPayload(form);

    try {
      if (editingMovie?.id) {
        await updateMovie(editingMovie.id, payload);
      } else {
        await createMovie(payload);
      }
      await refreshCatalog();
      setShowModal(false);
      pushToast({
        title: "Movie saved",
        message: editingMovie ? "Movie details updated successfully." : "Movie added to catalog.",
      });
    } catch (error) {
      pushToast({
        title: "Save failed",
        message: error.message || "Unable to save movie.",
      });
    }
  };

  const handleDelete = async () => {
    if (!movieToDelete?.id) return;
    try {
      await deleteMovie(movieToDelete.id);
      await refreshCatalog();
      setShowConfirm(false);
      pushToast({ title: "Movie deleted", message: "Movie removed from listing." });
    } catch (error) {
      pushToast({
        title: "Delete failed",
        message: error.message || "Unable to delete movie.",
      });
    }
  };

  return (
    <>
      <AdminPageHeader
        title="Manage Movies"
        subtitle="Admin controls the full movie catalogue and metadata."
      >
        <button type="button" className="btn btn-primary admin-btn" onClick={openAdd}>
          <Plus size={16} className="me-2" />
          Add Movie
        </button>
      </AdminPageHeader>

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div className="d-flex gap-2 flex-wrap">
            <input className="form-control" placeholder="Search by title" />
            <select className="form-select">
              <option>Status</option>
              <option>Now Showing</option>
              <option>Coming Soon</option>
              <option>Premiere</option>
              <option>Ending Soon</option>
              <option>Archived</option>
            </select>
            <select className="form-select">
              <option>Language</option>
              <option>Nepali</option>
              <option>English</option>
              <option>Hindi</option>
            </select>
          </div>
          <div className="text-muted small">Showing {movies.length} movies</div>
        </div>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Poster</th>
                <th>Title</th>
                <th>Duration</th>
                <th>Genre</th>
                <th>Language</th>
                <th>Rating</th>
                <th>Release Date</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {movies.map((movie) => (
                <tr key={movie.id}>
                  <td>
                    <div className="admin-poster" style={{ background: movie.posterTone || pickPosterTone() }}>
                      {String(movie.title || "")
                        .split(" ")
                        .filter(Boolean)
                        .map((word) => word[0])
                        .join("")}
                    </div>
                  </td>
                  <td>
                    <div className="fw-semibold">{movie.title}</div>
                    <small className="text-muted">{movie.id}</small>
                  </td>
                  <td>{movie.duration}</td>
                  <td>{movie.genre}</td>
                  <td>{movie.language}</td>
                  <td>{movie.rating}</td>
                  <td>{movie.releaseDate}</td>
                  <td>
                    <span className={`badge-soft ${statusTone(movie.status)}`}>
                      {formatStatusLabel(movie.status)}
                    </span>
                  </td>
                  <td>
                    <div className="d-flex gap-2">
                      <button type="button" className="btn btn-outline-light btn-sm">
                        <Eye size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => openEdit(movie)}
                      >
                        <Pencil size={16} />
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => {
                          setMovieToDelete(movie);
                          setShowConfirm(true);
                        }}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {movies.length === 0 ? (
                <tr>
                  <td colSpan="9">No movies added yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <nav className="d-flex justify-content-between align-items-center mt-3">
          <span className="text-muted small">Page 1 of 1</span>
          <ul className="pagination mb-0">
            <li className="page-item disabled"><span className="page-link">Prev</span></li>
            <li className="page-item active"><span className="page-link">1</span></li>
            <li className="page-item disabled"><span className="page-link">Next</span></li>
          </ul>
        </nav>
      </section>

      <AdminModal
        show={showModal}
        title={editingMovie ? "Edit Movie" : "Add Movie"}
        onClose={() => setShowModal(false)}
        footer={
          <>
            <button type="button" className="btn btn-outline-light" onClick={() => setShowModal(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" onClick={handleSave} disabled={formLoading}>
              Save Movie
            </button>
          </>
        }
      >
        <MovieForm
          value={form}
          loading={formLoading}
          onChange={setForm}
          onEditPerson={(personId) => {
            if (!personId) return;
            navigate(`/admin/people?personId=${encodeURIComponent(personId)}`);
          }}
        />
      </AdminModal>

      <ConfirmModal
        show={showConfirm}
        title="Delete movie?"
        description="This action will remove the movie from all schedules."
        onCancel={() => setShowConfirm(false)}
        onConfirm={handleDelete}
      />
    </>
  );
}

function safeUseAppContext() {
  try {
    return useAppContext?.();
  } catch {
    return null;
  }
}

function buildEmptyMovie() {
  return {
    title: "",
    duration: "",
    genre: "",
    language: "",
    rating: "",
    releaseDate: "",
    status: "COMING_SOON",
    synopsis: "",
    posterUrl: "",
    trailerUrl: "",
    cast: [],
    crew: [],
  };
}

function buildFormFromMovie(movie) {
  const cast = Array.isArray(movie?.cast)
    ? movie.cast.map((credit, index) => toCreditForm(credit, index, "CAST"))
    : [];
  const crew = Array.isArray(movie?.crew)
    ? movie.crew.map((credit, index) => toCreditForm(credit, index, "CREW"))
    : [];
  return {
    title: movie?.title || "",
    duration: movie?.duration || "",
    genre: movie?.genre || "",
    language: movie?.language || "",
    rating: movie?.rating || "",
    releaseDate: movie?.releaseDate || movie?.release_date || "",
    status: movie?.status || "COMING_SOON",
    synopsis: movie?.description || movie?.synopsis || "",
    posterUrl: movie?.posterUrl || movie?.poster_url || "",
    trailerUrl: movie?.trailerUrl || movie?.trailer_url || "",
    cast,
    crew,
  };
}

function toCreditForm(credit, index, roleType) {
  const person = credit?.person || {};
  const name =
    person?.fullName ||
    person?.full_name ||
    person?.name ||
    credit?.name ||
    "";
  const role =
    credit?.characterName ||
    credit?.jobTitle ||
    credit?.roleName ||
    credit?.department ||
    credit?.role ||
    "";
  return {
    id: credit?.id,
    position: credit?.position ?? credit?.order ?? index + 1,
    personId: person?.id || credit?.personId || "",
    name,
    role,
    roleType: credit?.roleType || credit?.creditType || roleType,
  };
}

function buildCreditsPayload(form) {
  const buildPayload = (items = [], roleType) =>
    items.map((credit, index) => {
      const position = Number(credit.position) || index + 1;
      const name = String(credit.name || "").trim();
      if (credit.personId) {
        return {
          id: credit.id,
          role_type: roleType,
          character_name: roleType === "CAST" ? credit.role || "" : "",
          job_title: roleType === "CREW" ? credit.role || "" : "",
          position,
          person_id: Number(credit.personId),
        };
      }
      return {
        id: credit.id,
        role_type: roleType,
        character_name: roleType === "CAST" ? credit.role || "" : "",
        job_title: roleType === "CREW" ? credit.role || "" : "",
        position,
        person: {
          full_name: name,
        },
      };
    });
  const castPayload = buildPayload(form?.cast || [], "CAST");
  const crewPayload = buildPayload(form?.crew || [], "CREW");
  return [...castPayload, ...crewPayload];
}

function validateCredits(form) {
  const allCredits = [...(form.cast || []), ...(form.crew || [])];
  for (const credit of allCredits) {
    if (!credit.personId && !String(credit.name || "").trim()) {
      return "Each cast/crew entry must have a name.";
    }
    if (!String(credit.role || "").trim()) {
      return "Each cast/crew entry must have a role.";
    }
  }
  return "";
}

function formatStatusLabel(status) {
  if (status === "NOW_SHOWING") return "Now Showing";
  if (status === "COMING_SOON") return "Coming Soon";
  return status || "Unknown";
}

function statusTone(status) {
  if (status === "NOW_SHOWING") return "success";
  if (status === "COMING_SOON") return "info";
  return "info";
}

function pickPosterTone() {
  const tones = [
    "linear-gradient(135deg, #6d8bff, #2f3b7c)",
    "linear-gradient(135deg, #22d3ee, #0f766e)",
    "linear-gradient(135deg, #f43f5e, #9f1239)",
    "linear-gradient(135deg, #34d399, #047857)",
    "linear-gradient(135deg, #fbbf24, #b45309)",
    "linear-gradient(135deg, #60a5fa, #1d4ed8)",
  ];
  return tones[Math.floor(Math.random() * tones.length)];
}
