import { useMemo, useState } from "react";
import { Play, Plus, Trash2, AlertCircle } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import { useAdminToast } from "./AdminToastContext";
import { useAppContext } from "../context/Appcontext";
import { isNowShowingStatus, isComingSoonStatus } from "../lib/showUtils";
import { updateMovieTrailer, updateMovie } from "../lib/catalogApi";

// Helper: Extract YouTube video ID from various YouTube URL formats
function extractYouTubeId(url) {
  const patterns = [
    /(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)/,
    /youtube\.com\/.*[?&]v=([^&\n?#]+)/,
  ];
  for (const pattern of patterns) {
    const match = url.match(pattern);
    if (match && match[1]) return match[1];
  }
  return null;
}

// Helper: Generate YouTube thumbnail URL from video ID
function getYouTubePosterUrl(videoId) {
  if (!videoId) return null;
  // Use maxresdefault for highest quality; falls back to hqdefault if unavailable
  return `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg`;
}

export default function AdminTrailers() {
  const { pushToast } = useAdminToast();
  const ctx = safeUseAppContext();
  const movies = ctx?.movies ?? [];
  const refreshCatalog = ctx?.refreshCatalog ?? (async () => {});

  const [selectedMovieId, setSelectedMovieId] = useState("");
  const [trailerUrl, setTrailerUrl] = useState("");
  const [saving, setSaving] = useState(false);
  const [query, setQuery] = useState("");

  // Compute YouTube poster preview
  const youTubePosterId = extractYouTubeId(trailerUrl);
  const youTubePosterUrl = youTubePosterId ? getYouTubePosterUrl(youTubePosterId) : null;

  const homeMovies = useMemo(() => {
    const base = Array.isArray(movies) ? movies : [];
    return base.filter((movie) => {
      const status = movie?.listingStatus || movie?.status;
      return isNowShowingStatus(status) || isComingSoonStatus(status);
    });
  }, [movies]);

  const trailerRows = useMemo(() => {
    return homeMovies
      .filter((movie) => String(movie?.trailerUrl || movie?.trailer_url || "").trim())
      .filter((movie) => {
        const text = query.trim().toLowerCase();
        if (!text) return true;
        const title = String(movie?.title || "").toLowerCase();
        return title.includes(text);
      });
  }, [homeMovies, query]);

  const handleAddOrUpdate = async () => {
    const movieId = Number(selectedMovieId);
    if (!Number.isInteger(movieId) || movieId <= 0) {
      pushToast({ title: "Select movie", message: "Please choose an existing movie." });
      return;
    }
    const trimmed = String(trailerUrl || "").trim();
    if (!trimmed) {
      pushToast({ title: "Missing URL", message: "Please enter a trailer URL." });
      return;
    }

    // Extract YouTube ID and validate
    const youTubeId = extractYouTubeId(trimmed);
    if (!youTubeId) {
      pushToast({
        title: "Invalid YouTube URL",
        message: "Please provide a valid YouTube URL.",
      });
      return;
    }

    setSaving(true);
    try {
      // Get YouTube poster URL
      const posterUrl = getYouTubePosterUrl(youTubeId);

      // Update movie with both trailer URL and YouTube poster
      await updateMovie(movieId, {
        trailer_url: trimmed,
        poster_url: posterUrl,
      });

      await refreshCatalog();
      setSelectedMovieId("");
      setTrailerUrl("");
      pushToast({
        title: "Trailer saved",
        message: "Trailer and YouTube poster added to Home section.",
      });
    } catch (error) {
      pushToast({
        title: "Save failed",
        message: error.message || "Unable to save trailer.",
      });
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = async (movieId) => {
    if (!movieId) return;
    setSaving(true);
    try {
      await updateMovieTrailer(movieId, "");
      await refreshCatalog();
      pushToast({ title: "Trailer removed", message: "Trailer removed from Home section." });
    } catch (error) {
      pushToast({
        title: "Remove failed",
        message: error.message || "Unable to remove trailer.",
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <AdminPageHeader
        title="Manage Trailers"
        subtitle="Add trailer URL for Now Showing and Coming Soon movies on Home page."
      />

      <section className="admin-card mb-3">
        <div className="row g-2 align-items-end">
          <div className="col-md-5">
            <label className="form-label">Movie</label>
            <select
              className="form-select"
              value={selectedMovieId}
              onChange={(event) => setSelectedMovieId(event.target.value)}
              disabled={saving}
            >
              <option value="">Select existing movie</option>
              {homeMovies.map((movie) => (
                <option key={movie.id} value={movie.id}>
                  {movie.title}
                </option>
              ))}
            </select>
          </div>
          <div className="col-md-5">
            <label className="form-label">Trailer URL (YouTube)</label>
            <input
              className="form-control"
              type="url"
              placeholder="https://www.youtube.com/watch?v=..."
              value={trailerUrl}
              onChange={(event) => setTrailerUrl(event.target.value)}
              disabled={saving}
            />
            {trailerUrl && !youTubePosterId && (
              <div className="text-danger small d-flex gap-1 align-items-center mt-2">
                <AlertCircle size={14} />
                Invalid YouTube URL format
              </div>
            )}
          </div>
          <div className="col-md-2">
            <button
              type="button"
              className="btn btn-primary w-100"
              onClick={handleAddOrUpdate}
              disabled={saving || !youTubePosterId}
            >
              <Plus size={16} className="me-2" />
              Save
            </button>
          </div>
        </div>

        {youTubePosterUrl && (
          <div className="row g-3 mt-2">
            <div className="col-md-12">
              <label className="form-label text-muted small">YouTube Poster Preview</label>
              <img
                src={youTubePosterUrl}
                alt="YouTube poster preview"
                style={{
                  maxWidth: "200px",
                  maxHeight: "112px",
                  borderRadius: "4px",
                  border: "1px solid #ddd",
                }}
              />
              <div className="text-muted small mt-2">
                This poster will be automatically set for the movie
              </div>
            </div>
          </div>
        )}
      </section>

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <input
            className="form-control"
            style={{ maxWidth: 320 }}
            placeholder="Search trailer by title"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <div className="text-muted small">Active trailers: {trailerRows.length}</div>
        </div>

        <div className="table-responsive">
          <table className="table admin-table">
            <thead>
              <tr>
                <th>Movie</th>
                <th>Trailer URL</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {trailerRows.map((movie) => {
                const trailer = movie?.trailerUrl || movie?.trailer_url || "";
                return (
                  <tr key={movie.id}>
                    <td>
                      <div className="fw-semibold d-flex align-items-center gap-2">
                        <Play size={16} />
                        {movie.title}
                      </div>
                    </td>
                    <td>
                      <a href={trailer} target="_blank" rel="noreferrer">
                        {trailer}
                      </a>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-outline-danger btn-sm"
                        onClick={() => handleRemove(movie.id)}
                        disabled={saving}
                      >
                        <Trash2 size={15} className="me-1" />
                        Remove
                      </button>
                    </td>
                  </tr>
                );
              })}
              {trailerRows.length === 0 ? (
                <tr>
                  <td colSpan="3">No trailer configured yet for Home movies.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
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
