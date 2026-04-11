import { useEffect, useMemo, useState } from "react";
import { Eye, Pencil, Plus, Trash2 } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import AdminPageHeader from "./components/AdminPageHeader";
import AdminModal from "./components/AdminModal";
import ConfirmModal from "./components/ConfirmModal";
import MovieForm from "./components/MovieForm";
import { useAdminToast } from "./AdminToastContext";
import { createMovie, deleteMovie, fetchMovieById, updateMovie } from "../lib/catalogApi";
import { useAppContext } from "../context/Appcontext";

export default function AdminMovies() {
  const PAGE_SIZE = 8;
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
  const [currentPage, setCurrentPage] = useState(1);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState("Status");
  const [languageFilter, setLanguageFilter] = useState("Language");
  const [flowFilter, setFlowFilter] = useState("all");
  const [searchParams] = useSearchParams();
  const queryFromUrl = String(searchParams.get("q") || "");

  useEffect(() => {
    setSearchTerm(queryFromUrl);
  }, [queryFromUrl]);

  const filteredMovies = useMemo(() => {
    let list = [...movies];

    if (searchTerm.trim()) {
      const term = searchTerm.trim().toLowerCase();
      list = list.filter((movie) =>
        String(movie.title || "").toLowerCase().includes(term)
      );
    }

    if (statusFilter !== "Status") {
      list = list.filter((movie) => {
        const label = formatStatusLabel(movie.status);
        return label === statusFilter;
      });
    }

    if (languageFilter !== "Language") {
      list = list.filter(
        (movie) => String(movie.language || "") === languageFilter
      );
    }

    if (flowFilter !== "all") {
      list = list.filter((movie) => {
        const isVendorSubmission = isVendorSubmissionMovie(movie);
        return flowFilter === "published" ? !isVendorSubmission : isVendorSubmission;
      });
    }

    return list;
  }, [movies, searchTerm, statusFilter, languageFilter, flowFilter]);

  const moderationStats = useMemo(() => {
    const published = movies.filter((movie) => !isVendorSubmissionMovie(movie)).length;
    const submissions = movies.filter((movie) => isVendorSubmissionMovie(movie)).length;
    const pending = movies.filter((movie) => String(movie?.approvalStatus || movie?.approval_status || "").trim().toUpperCase() === "PENDING").length;
    return { published, submissions, pending };
  }, [movies]);

  const totalPages = Math.max(1, Math.ceil(filteredMovies.length / PAGE_SIZE));
  const paginatedMovies = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filteredMovies.slice(start, start + PAGE_SIZE);
  }, [filteredMovies, currentPage]);

  useEffect(() => {
    setCurrentPage((prev) => Math.min(prev, totalPages));
  }, [totalPages]);


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

    const payload = buildMovieFormData(form);

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
        <div className="d-flex flex-wrap gap-2 mb-3">
          <button type="button" className={`btn btn-sm ${flowFilter === "all" ? "btn-primary" : "btn-outline-light"}`} onClick={() => setFlowFilter("all")}>
            All flows
          </button>
          <button type="button" className={`btn btn-sm ${flowFilter === "published" ? "btn-primary" : "btn-outline-light"}`} onClick={() => setFlowFilter("published")}>
            Published catalog
          </button>
          <button type="button" className={`btn btn-sm ${flowFilter === "submitted" ? "btn-primary" : "btn-outline-light"}`} onClick={() => setFlowFilter("submitted")}>
            Vendor submissions
          </button>
        </div>
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div className="d-flex gap-2 flex-wrap admin-filter-row">
            <input
              className="form-control"
              placeholder="Search by title"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
            />
            <select
              className="form-select"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option>Status</option>
              <option>Now Showing</option>
              <option>Coming Soon</option>
              <option>Premiere</option>
              <option>Ending Soon</option>
              <option>Archived</option>
            </select>
            <select
              className="form-select"
              value={languageFilter}
              onChange={(event) => setLanguageFilter(event.target.value)}
            >
              <option>Language</option>
              <option>Nepali</option>
              <option>English</option>
              <option>Hindi</option>
            </select>
          </div>
          <div className="text-muted small">
            Showing {filteredMovies.length} movies | Published {moderationStats.published} | Vendor submissions {moderationStats.submissions} | Pending review {moderationStats.pending}
          </div>
        </div>
        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Poster</th>
                <th>ID</th>
                <th>Title</th>
                <th>Flow</th>
                <th>Approval</th>
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
              {paginatedMovies.map((movie) => {
                const posterUrl = resolveMoviePoster(movie);
                const posterInitials = getMovieInitials(movie.title);
                return (
                  <tr key={movie.id}>
                    <td>
                      <div className="admin-poster" style={{ background: movie.posterTone || pickPosterTone() }}>
                        <span className="admin-posterFallback">{posterInitials}</span>
                        {posterUrl ? (
                          <img
                            className="admin-posterImage"
                            src={posterUrl}
                            alt={`${movie.title || "Movie"} poster`}
                            loading="lazy"
                            onError={(event) => {
                              event.currentTarget.style.display = "none";
                            }}
                          />
                        ) : null}
                      </div>
                    </td>
                    <td>{movie.id}</td>
                  <td>
                    <div className="fw-semibold">{movie.title}</div>
                    {movie.approvalReason ? <div className="text-muted small">{movie.approvalReason}</div> : null}
                  </td>
                  <td>
                    <span className={`badge-soft ${isVendorSubmissionMovie(movie) ? "warning" : "success"}`}>
                      {isVendorSubmissionMovie(movie) ? "Vendor submission" : "Published catalog"}
                    </span>
                  </td>
                  <td>
                    <span className={`badge-soft ${approvalTone(movie.approvalStatus)}`}>
                      {formatApprovalLabel(movie.approvalStatus, movie.isApproved)}
                    </span>
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
                      <button
                        type="button"
                        className="btn btn-outline-light btn-sm"
                        onClick={() => openEdit(movie)}
                      >
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
                );
              })}
              {filteredMovies.length === 0 ? (
                <tr>
                  <td colSpan="12">No movies added yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <nav className="d-flex justify-content-between align-items-center mt-3">
          <span className="text-muted small">Page {currentPage} of {totalPages}</span>
          <ul className="pagination mb-0">
            <li className={`page-item ${currentPage === 1 ? "disabled" : ""}`}>
              <button
                type="button"
                className="page-link"
                onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                disabled={currentPage === 1}
              >
                Prev
              </button>
            </li>
            {Array.from({ length: totalPages }, (_, idx) => idx + 1).map((page) => (
              <li key={page} className={`page-item ${currentPage === page ? "active" : ""}`}>
                <button
                  type="button"
                  className="page-link"
                  onClick={() => setCurrentPage(page)}
                >
                  {page}
                </button>
              </li>
            ))}
            <li className={`page-item ${currentPage === totalPages ? "disabled" : ""}`}>
              <button
                type="button"
                className="page-link"
                onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                disabled={currentPage === totalPages}
              >
                Next
              </button>
            </li>
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
    posterFile: null,
    posterPreview: "",
    trailerUrlsText: "",
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
  const trailerUrls = Array.isArray(movie?.trailerUrls)
    ? movie.trailerUrls
    : Array.isArray(movie?.trailer_urls)
      ? movie.trailer_urls
      : [movie?.trailerUrl || movie?.trailer_url || ""];
  const normalizedTrailerUrls = trailerUrls
    .map((item) => String(item || "").trim())
    .filter(Boolean);

  return {
    title: movie?.title || "",
    duration: movie?.duration || "",
    genre: movie?.genre || "",
    language: movie?.language || "",
    rating: movie?.rating || "",
    releaseDate: movie?.releaseDate || movie?.release_date || "",
    status: movie?.status || "COMING_SOON",
    synopsis: movie?.description || movie?.synopsis || "",
    posterFile: null,
    posterPreview: movie?.posterImage || movie?.poster_image || movie?.posterUrl || movie?.poster_url || "",
    trailerUrlsText: normalizedTrailerUrls.join("\n"),
    cast,
    crew,
  };
}

function buildMovieFormData(form) {
  const payload = new FormData();
  payload.append("title", form.title.trim());
  payload.append("duration", form.duration.trim());
  payload.append("genre", form.genre.trim());
  payload.append("language", form.language.trim());
  payload.append("rating", form.rating.trim());
  payload.append("release_date", form.releaseDate || "");
  payload.append("status", form.status || "COMING_SOON");
  payload.append("description", form.synopsis?.trim() || "");
  const trailerUrls = String(form.trailerUrlsText || "")
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
  payload.append("trailer_urls", JSON.stringify(trailerUrls));
  payload.append("trailer_url", trailerUrls[0] || "");
  let photoCounter = 0;
  const appendPersonPhoto = (credit) => {
    if (!credit?.photoFile) return undefined;
    const key = `credit_person_photo_${photoCounter}`;
    photoCounter += 1;
    payload.append(key, credit.photoFile);
    return key;
  };
  payload.append("credits", JSON.stringify(buildCreditsPayload(form, appendPersonPhoto)));
  if (form.posterFile) {
    payload.append("poster_image", form.posterFile);
  }
  return payload;
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
  const photoUrl =
    person?.photoUrl ||
    person?.photo_url ||
    person?.photo ||
    credit?.photoUrl ||
    credit?.photo_url ||
    "";
  return {
    id: credit?.id,
    position: credit?.position ?? credit?.order ?? index + 1,
    personId: person?.id || credit?.personId || "",
    name,
    role,
    photoUrl,
    photoFile: null,
    roleType: credit?.roleType || credit?.creditType || roleType,
  };
}

function buildCreditsPayload(form, appendPersonPhoto) {
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
          photo_url: String(credit.photoUrl || "").trim() || undefined,
          photo_upload_key: appendPersonPhoto?.(credit),
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

function isVendorSubmissionMovie(movie) {
  const source = String(movie?.approvalMetadata?.source || movie?.approval_metadata?.source || "").toLowerCase();
  const approvalStatus = String(movie?.approvalStatus || movie?.approval_status || "").trim().toUpperCase();
  return source === "vendor_submission" || approvalStatus === "PENDING" || approvalStatus === "REJECTED";
}

function formatApprovalLabel(status, isApproved) {
  const approvalStatus = String(status || "").trim().toUpperCase();
  if (approvalStatus === "APPROVED") return "Approved";
  if (approvalStatus === "REJECTED") return "Rejected";
  if (approvalStatus === "PENDING") return "Pending review";
  return isApproved ? "Approved" : "Unknown";
}

function approvalTone(status) {
  const approvalStatus = String(status || "").trim().toUpperCase();
  if (approvalStatus === "APPROVED") return "success";
  if (approvalStatus === "REJECTED") return "danger";
  if (approvalStatus === "PENDING") return "warning";
  return "info";
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

function resolveMoviePoster(movie) {
  return (
    movie?.posterImage ||
    movie?.poster_image ||
    movie?.posterUrl ||
    movie?.poster_url ||
    movie?.poster ||
    ""
  );
}

function getMovieInitials(value) {
  const initials = String(value || "")
    .split(" ")
    .filter(Boolean)
    .map((word) => word[0])
    .join("")
    .slice(0, 3)
    .toUpperCase();
  return initials || "MOV";
}
