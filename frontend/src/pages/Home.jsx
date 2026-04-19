import React, { useEffect, useMemo, useState } from "react";
import "../css/home.css";
import { useNavigate } from "react-router-dom";
import { Film, Play } from "lucide-react";
import { useAppContext } from "../context/Appcontext";
import { fetchTrailers } from "../lib/catalogApi";
import { getNowShowing, resolveMoviesByShowListing } from "../lib/showUtils";
import HeroSlider from "../components/HeroSlider";
import CollaboratorsRow from "../components/CollaboratorsRow";
import NowShowingCard from "../components/NowShowingCard";

export default function Home() {
  const navigate = useNavigate();

  const ctx = safeUseAppContext();
  const movies = ctx?.movies ?? [];
  const showtimes = ctx?.showtimes ?? [];

  // Build set of movie IDs that have active shows
  const moviesWithActiveShows = useMemo(() => {
    if (!Array.isArray(showtimes) || showtimes.length === 0) return new Set();
    const movieIds = new Set();
    showtimes.forEach((show) => {
      const movieId = String(show.movieId || show.movie_id || "").trim();
      if (movieId) movieIds.add(movieId);
    });
    return movieIds;
  }, [showtimes]);

  const showBuckets = useMemo(
    () => resolveMoviesByShowListing(movies, showtimes),
    [movies, showtimes]
  );
  const visibleShows = useMemo(() => {
    if (moviesWithActiveShows.size === 0) {
      return getNowShowing(movies, 5).slice(0, 5);
    }

    const fromShows = (showBuckets?.nowShowing || []).filter((movie) => {
      const id = String(movie?.id || "").trim();
      return moviesWithActiveShows.has(id);
    });
    if (fromShows.length) return fromShows.slice(0, 5);

    const fallback = getNowShowing(movies, 5).filter((movie) => {
      const id = String(movie?.id || "").trim();
      return moviesWithActiveShows.has(id);
    });
    return fallback.slice(0, 5);
  }, [showBuckets, movies, moviesWithActiveShows]);


  // Only one trailer per movie (deduplicate by movie id)
  const [trailers, setTrailers] = useState([]);
  const [trailersLoading, setTrailersLoading] = useState(true);
  const [trailersError, setTrailersError] = useState("");
  const [currentTrailer, setCurrentTrailer] = useState(null);

  useEffect(() => {
    let mounted = true;
    const loadTrailers = async () => {
      setTrailersLoading(true);
      setTrailersError("");
      try {
        const list = await fetchTrailers();
        if (!mounted) return;
        // Deduplicate: only one trailer per movie (first found)
        if (Array.isArray(list)) {
          const seen = new Set();
          const unique = [];
          for (const t of list) {
            const movieId = t.movie_id || t.movieId || t.movie || t.id;
            if (movieId && !seen.has(movieId)) {
              seen.add(movieId);
              unique.push(t);
            }
          }
          setTrailers(unique);
        } else {
          setTrailers([]);
        }
      } catch (error) {
        if (!mounted) return;
        setTrailersError(error.message || "Unable to load trailers.");
      } finally {
        if (mounted) setTrailersLoading(false);
      }
    };
    loadTrailers();
    return () => {
      mounted = false;
    };
  }, []);

  const featuredTrailer = useMemo(
    () => trailers.find((item) => item.is_featured) || null,
    [trailers]
  );

  useEffect(() => {
    if (!trailers.length) {
      setCurrentTrailer(null);
      return;
    }
    setCurrentTrailer((prev) => {
      if (prev && trailers.some((item) => item.id === prev.id)) return prev;
      return featuredTrailer || trailers[0];
    });
  }, [trailers, featuredTrailer]);

  const activeTrailer = currentTrailer || featuredTrailer || trailers[0];

  return (
    <div className="wf2-page">
      {/* ===== HERO ===== */}
      <HeroSlider page="home" />
      <CollaboratorsRow />

      <section className="home-mediaWrap">
        {/* ===== NOW SHOWING ===== */}
        <section className="wf2-container wf2-section home-nowshowing">
          <div className="wf2-constrained">
            <div className="ns-head">
              <h3 className="ns-tab ns-tabActive">
                <Film size={18} />
                <span>Now Showing</span>
              </h3>
            </div>

            <div className="ns-grid">
              {visibleShows.length ? (
                visibleShows.map((movie) => (
                  <NowShowingCard
                    key={movie._id || movie.id || movie.title}
                    movie={movie}
                    onBuy={() =>
                      navigate(
                        `/movie/${movie?._id || movie?.id || encodeURIComponent(movie?.title || movie?.name || "")}`,
                        { state: { movie } }
                      )
                    }
                  />
                ))
              ) : (
                <div className="text-muted">No now showing movies yet.</div>
              )}
            </div>

            <div className="wf2-center">
              <button
                className="wf2-btn wf2-btnPrimary wf2-btnPill wf2-btnWide"
                onClick={() => navigate("/movies")}
              >
                Show more
              </button>
            </div>
          </div>
        </section>

        {/* ===== TRAILERS ===== */}
        {trailersLoading || trailersError || trailers.length ? (
          <section className="wf2-container wf2-section home-trailers">
            <div className="wf2-constrained">
              <div className="ns-head">
                <h3 className="ns-tab ns-tabActive">
                  <Play size={18} />
                  <span>Trailers</span>
                </h3>
              </div>

              {trailersLoading ? (
                <div className="wf2-trailerLayout">
                  <div className="wf2-trailerPlayer">
                    <div className="wf2-trailerMain wf2-skeleton" />
                    <div className="wf2-trailerMeta">
                      <div className="wf2-skeleton wf2-skeleton-line" />
                    </div>
                  </div>
                  <aside className="wf2-trailerSide">
                    <div className="wf2-trailerThumbs">
                      {Array.from({ length: 3 }).map((_, i) => (
                        <div key={i} className="wf2-thumbBtn wf2-thumbSkeleton">
                          <div className="wf2-thumbMedia">
                            <div className="wf2-skeleton wf2-skeleton-thumb" />
                          </div>
                          <div className="wf2-thumbInfo">
                            <div className="wf2-skeleton wf2-skeleton-line" />
                            <div className="wf2-skeleton wf2-skeleton-line small" />
                          </div>
                        </div>
                      ))}
                    </div>
                  </aside>
                </div>
              ) : trailersError ? (
                <div className="wf2-trailerEmpty">{trailersError}</div>
              ) : trailers.length ? (
                <div className="wf2-trailerLayout">
                  <div className="wf2-trailerPlayer">
                    <div className="wf2-trailerMain">
                      <iframe
                        src={getEmbedUrl(activeTrailer)}
                        title={activeTrailer?.title || "Trailer"}
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                        referrerPolicy="strict-origin-when-cross-origin"
                        loading="lazy"
                        allowFullScreen
                      />
                    </div>
                    <div className="wf2-trailerMeta">
                      <h4 className="wf2-trailerTitle">{activeTrailer?.title || "Trailer"}</h4>
                    </div>
                  </div>

                  <aside className="wf2-trailerSide">
                    <div className="wf2-trailerThumbs">
                      {trailers.map((t, i) => (
                        <button
                          key={t.id || i}
                          className={`wf2-thumbBtn ${activeTrailer?.id === t.id ? "wf2-thumbActive" : ""}`}
                          onClick={() => setCurrentTrailer(t)}
                          aria-label={t.title || `Trailer ${i + 1}`}
                          type="button"
                        >
                          <div className="wf2-thumbMedia">
                            <img
                              src={getTrailerThumbnail(t)}
                              alt={t.title || `Trailer ${i + 1}`}
                              loading="lazy"
                              decoding="async"
                            />
                            {t.duration_label ? (
                              <span className="wf2-thumbDuration">{t.duration_label}</span>
                            ) : null}
                          </div>
                          <div className="wf2-thumbInfo">
                            <div className="wf2-thumbTitle">{t.title || `Trailer ${i + 1}`}</div>
                          </div>
                        </button>
                      ))}
                    </div>
                  </aside>
                </div>
              ) : (
                <div className="wf2-trailerEmpty">No trailers available right now.</div>
              )}
            </div>
          </section>
        ) : null}
      </section>

      {/* Footer removed to avoid duplicate — global Footer renders from Layout */}
    </div>
  );
}

/* helpers */
function safeUseAppContext() {
  try {
    return useAppContext?.();
  } catch {
    return null;
  }
}

function toEmbedUrl(url) {
  if (!url) return "";
  try {
    const match = url.match(/(?:v=)([0-9A-Za-z_-]{11})(?:[&?]|$)\s*/);
    const shortMatch = url.match(/youtu\.be\/([0-9A-Za-z_-]{11})/);
    const match2 = url.match(/\/([0-9A-Za-z_-]{11})(?:\?|$)/);
    const id = (match && match[1]) || (shortMatch && shortMatch[1]) || (match2 && match2[1]);
    if (id) return `https://www.youtube.com/embed/${id}?rel=0`;
  } catch {}
  return url;
}

function getEmbedUrl(trailer) {
  if (!trailer) return "";
  if (trailer.youtube_id) {
    return `https://www.youtube.com/embed/${trailer.youtube_id}?rel=0`;
  }
  return toEmbedUrl(trailer.youtube_url || "");
}

function getTrailerThumbnail(trailer) {
  if (!trailer) return "";
  if (trailer.youtube_id) {
    return `https://img.youtube.com/vi/${trailer.youtube_id}/hqdefault.jpg`;
  }
  if (trailer.thumbnail_url) return trailer.thumbnail_url;
  return "";
}

// fallback posters are handled in NowShowingCard when data is missing
