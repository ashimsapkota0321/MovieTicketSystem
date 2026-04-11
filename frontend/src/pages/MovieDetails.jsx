import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Heart, Play, Star } from "lucide-react";

import "../css/movieDetails.css";
import "../css/home.css";
import AdultWarningModal from "../components/AdultWarningModal";
import {
  createMovieReview,
  deleteMovieReview,
  fetchMovieById,
  fetchMovieBySlug,
  fetchPersonDetail,
  updateMovieReview,
} from "../lib/catalogApi";
import { getMovieRatingLabel, isAdultRating } from "../lib/showUtils";
import { useAppContext } from "../context/Appcontext";

export default function MovieDetails() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const ctx = safeUseAppContext();
  const allMovies = Array.isArray(ctx?.movies) ? ctx.movies : [];

  const [movie, setMovie] = useState(() => location?.state?.movie || null);
  const [loading, setLoading] = useState(!location?.state?.movie);
  const [loadError, setLoadError] = useState("");
  const isComingSoon = Boolean(location?.state?.variant === "soon" || location?.state?.isComingSoon);
  const [currentTrailer, setCurrentTrailer] = useState("");
  const [isTrailerOpen, setTrailerOpen] = useState(false);
  const [reviewRating, setReviewRating] = useState(0);
  const [reviewComment, setReviewComment] = useState("");
  const [editingReviewId, setEditingReviewId] = useState(null);
  const [reviewStatus, setReviewStatus] = useState("");
  const [selectedPerson, setSelectedPerson] = useState(null);
  const [selectedCredit, setSelectedCredit] = useState(null);
  const [personLoading, setPersonLoading] = useState(false);
  const [personError, setPersonError] = useState("");
  const [adultConfirmOpen, setAdultConfirmOpen] = useState(false);

  useEffect(() => {
    let mounted = true;
    const hasStateMovie = Boolean(location?.state?.movie);

    const loadMovie = async () => {
      // Keep existing state movie visible while details hydrate in the background.
      setLoading(!hasStateMovie);
      setLoadError("");
      try {
        const isNumeric = /^\d+$/.test(String(id || ""));
        const data = isNumeric ? await fetchMovieById(id) : await fetchMovieBySlug(id);
        if (!mounted) return;
        setMovie(data || null);
      } catch (error) {
        if (!mounted) return;
        // Preserve state movie if available; otherwise show load failure.
        if (!hasStateMovie) {
          setMovie(null);
          setLoadError(error.message || "Unable to load movie.");
        }
      } finally {
        if (mounted) setLoading(false);
      }
    };

    loadMovie();
    return () => {
      mounted = false;
    };
  }, [id, location?.state?.movie]);

  const activeMovie = movie;
  const trailerUrls = resolveTrailerUrls(activeMovie);
  const trailerUrl = trailerUrls[0] || "";

  const title = activeMovie?.title || activeMovie?.name || "Movie Title";
  const poster =
    activeMovie?.posterImage ||
    activeMovie?.poster ||
    activeMovie?.posterUrl ||
    activeMovie?.image ||
    "";
  const language = toText(activeMovie?.language || activeMovie?.lang) || "Unknown";
  const averageRating = Number(activeMovie?.averageRating ?? 0);
  const reviewCount = Number(activeMovie?.reviewCount ?? (Array.isArray(activeMovie?.reviews) ? activeMovie.reviews.length : 0));
  const ratingValue = formatRating(averageRating) || "0.0";
  const description =
    toText(
      activeMovie?.description ||
        activeMovie?.shortDescription ||
        activeMovie?.longDescription ||
        activeMovie?.overview ||
        activeMovie?.synopsis
    ) || "No description available yet.";
  const duration = formatDuration(activeMovie?.duration || activeMovie?.runtime);
  const genres = toText(
    Array.isArray(activeMovie?.genres)
      ? activeMovie.genres.map((g) => g?.name).filter(Boolean).join(", ")
      : activeMovie?.genre || activeMovie?.category
  );
  const year = formatYear(activeMovie?.year || activeMovie?.releaseDate || activeMovie?.premiere);
  const metaParts = [duration, genres, year].filter(Boolean);
  const metaLine = metaParts.length > 0 ? metaParts.join(" | ") : "";

  const cast = useMemo(() => resolveCredits(activeMovie, "CAST"), [activeMovie]);

  const crew = useMemo(() => resolveCredits(activeMovie, "CREW"), [activeMovie]);

  const reviews = useMemo(() => resolveReviews(activeMovie), [activeMovie]);

  const similarMovies = useMemo(() => {
    if (!Array.isArray(allMovies) || !allMovies.length) return [];
    const currentId = String(activeMovie?.id || activeMovie?._id || "");
    const currentSlug = activeMovie?.slug || "";
    return allMovies.filter((item) => {
      if (!item) return false;
      const itemId = String(item.id || item._id || "");
      if (currentId && itemId && itemId === currentId) return false;
      if (currentSlug && item.slug && item.slug === currentSlug) return false;
      return true;
    });
  }, [allMovies, activeMovie]);

  const releaseLabel = formatDateLabel(
    activeMovie?.releaseDate || activeMovie?.premiere || activeMovie?.showDate || activeMovie?.date
  );
  const releaseValue = releaseLabel || "TBA";
  const ageRating = getMovieRatingLabel(activeMovie) || "PG";
  const isAdultMovie = isAdultRating(ageRating);
  const runtimeLabel = formatDuration(activeMovie?.duration || activeMovie?.runtime) || "TBA";
  const yearLabel = formatYear(activeMovie?.year || activeMovie?.releaseDate || activeMovie?.premiere) || "TBA";
  const genresLabel = genres || "Drama";
  const originalTitle = toText(activeMovie?.originalTitle) || title;
  const directorLabel = getDirectorLabel(activeMovie, crew) || "TBA";
  const castLabel = getCastLabel(cast) || "TBA";
  const trailerLang = getTrailerLang(language);
  const hasMultipleTrailers = trailerUrls.length > 1;
  const scheduleKey =
    activeMovie?.slug ||
    activeMovie?.id ||
    activeMovie?._id ||
    id ||
    encodeURIComponent(title);
  const handleTrailerAction = (preferredUrl = "") => {
    if (!trailerUrls.length) return;
    const initialUrl =
      hasMultipleTrailers && preferredUrl && trailerUrls.includes(preferredUrl)
        ? preferredUrl
        : trailerUrls[0];
    if (!initialUrl) return;
    setCurrentTrailer(initialUrl);
    setTrailerOpen(true);
  };

  const closeTrailer = () => {
    setTrailerOpen(false);
    setCurrentTrailer("");
  };

  const navigateToSchedule = () => {
    navigate(`/movie/${encodeURIComponent(scheduleKey)}/schedule`, {
      state: { movie: activeMovie },
    });
  };

  const handleBuyTickets = () => {
    if (isAdultMovie) {
      setAdultConfirmOpen(true);
      return;
    }
    navigateToSchedule();
  };

  const currentUser = getStoredUser();
  const handleReviewSubmit = async () => {
    setReviewStatus("");
    if (!currentUser?.id) {
      setReviewStatus("Please log in to submit a review.");
      return;
    }
    if (!reviewRating || reviewRating < 1) {
      setReviewStatus("Please select a rating.");
      return;
    }
    if (!movie?.id) {
      setReviewStatus("Movie is not ready yet.");
      return;
    }
    try {
      if (editingReviewId) {
        await updateMovieReview(editingReviewId, {
          rating: reviewRating,
          comment: reviewComment,
        });
        const refreshed = await fetchMovieById(movie.id);
        if (refreshed) setMovie(refreshed);
        setReviewStatus("Review updated.");
      } else {
        const updated = await createMovieReview(movie.id, {
          userId: currentUser.id,
          rating: reviewRating,
          comment: reviewComment,
        });
        setMovie(updated);
        setReviewStatus("Review submitted.");
      }
      setReviewComment("");
      setReviewRating(0);
      setEditingReviewId(null);
    } catch (error) {
      setReviewStatus(error.message || "Unable to submit review.");
    }
  };

  const handleReviewEdit = (review) => {
    if (!review?.id) return;
    setEditingReviewId(review.id);
    setReviewRating(Number(review.rating || 0));
    setReviewComment(review.comment || "");
    setReviewStatus("Editing your review.");
  };

  const handleReviewDelete = async (review) => {
    if (!review?.id || !movie?.id) return;
    setReviewStatus("");
    try {
      await deleteMovieReview(review.id);
      const refreshed = await fetchMovieById(movie.id);
      if (refreshed) setMovie(refreshed);
      if (editingReviewId === review.id) {
        setEditingReviewId(null);
        setReviewComment("");
        setReviewRating(0);
      }
      setReviewStatus("Review deleted.");
    } catch (error) {
      setReviewStatus(error.message || "Unable to delete review.");
    }
  };

  const openPerson = async (credit) => {
    const person = credit?.person || credit;
    if (!person?.slug) return;
    setSelectedCredit({
      roleType: credit?.roleType || credit?.creditType,
      characterName: credit?.characterName || credit?.roleName,
      jobTitle: credit?.jobTitle || credit?.department,
      movieId: activeMovie?.id,
    });
    setPersonError("");
    setPersonLoading(true);
    setSelectedPerson(null);
    try {
      const data = await fetchPersonDetail(person.slug);
      setSelectedPerson(data || null);
    } catch (error) {
      setPersonError(error.message || "Unable to load person details.");
    } finally {
      setPersonLoading(false);
    }
  };

  const closePerson = () => {
    setSelectedPerson(null);
    setSelectedCredit(null);
    setPersonError("");
    setPersonLoading(false);
  };

  const infoRows = [
    { label: "Original Title", value: originalTitle },
    { label: "Release Date", value: releaseValue },
    { label: "Age Rating", value: ageRating },
    { label: "Runtime", value: runtimeLabel },
    { label: "Year", value: yearLabel },
    { label: "Original Language", value: language },
    { label: "Genres", value: genresLabel },
    { label: "Director", value: directorLabel },
    { label: "Cast", value: castLabel },
    {
      label: "Trailer",
      value: (
        <button
          className="md-soonTrailer"
          type="button"
          onClick={() => handleTrailerAction(trailerUrl)}
          aria-label="Play trailer"
          disabled={!trailerUrl}
        >
          <span className="md-soonPlay">
            <Play size={12} />
          </span>
          <span className="md-soonTrailerText">{trailerLang}</span>
        </button>
      ),
    },
  ];

  if (loading) {
    return (
      <div className="md-page">
        <div className="md-state">Loading movie...</div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="md-page">
        <div className="md-state">{loadError}</div>
      </div>
    );
  }

  if (!activeMovie) {
    return (
      <div className="md-page">
        <div className="md-state">Movie not found.</div>
      </div>
    );
  }

  return (
    <div className={`md-page ${isComingSoon ? "md-soonPage" : ""}`}>
      <div className="md-container">
        {isComingSoon ? (
          <div className="md-soonPanel">
            <section className="md-soonHero">
              <div className="md-soonPoster">
                {poster ? <img src={poster} alt={title} /> : <div className="md-posterPlaceholder">No poster</div>}
              </div>
              <div className="md-soonContent">
                <h1 className="md-soonTitle">{title}</h1>
                <p className="md-soonDesc">{description}</p>
                <dl className="md-soonMeta">
                  {infoRows.map((row) => (
                    <React.Fragment key={row.label}>
                      <dt>{row.label}</dt>
                      <dd>{row.value}</dd>
                    </React.Fragment>
                  ))}
                </dl>
              </div>
            </section>
            <div className="md-soonDivider" />
            {releaseLabel ? (
              <div className="md-soonRelease">
                From <span className="md-soonReleaseDate">{releaseLabel}</span>
              </div>
            ) : null}
          </div>
        ) : (
          <>
            <section className="md-hero">
              <div className="md-posterWrap">
                {poster ? <img src={poster} alt={title} /> : <div className="md-posterPlaceholder">No poster</div>}
              </div>

              <div className="md-info">
                <div className="md-lang">{language}</div>
                <h1 className="md-title">{title}</h1>

                <div className="md-rating">
                  <Star size={16} />
                  <span>
                    {ratingValue} User Rating {reviewCount ? `(${reviewCount})` : ""}
                  </span>
                </div>

                <p className="md-desc">{description}</p>
                {metaLine ? <div className="md-meta">{metaLine}</div> : null}

                <div className="md-actions">
                  <button
                    className="md-btn md-btnGhost"
                    type="button"
                    onClick={() => handleTrailerAction(trailerUrl)}
                    disabled={!trailerUrl}
                  >
                    <span className="md-btnIcon">
                      <Play size={14} />
                    </span>
                    Watch Trailer{trailerUrls.length > 1 ? ` (${trailerUrls.length})` : ""}
                  </button>
                  <button
                    className="md-btn md-btnPrimary"
                    type="button"
                    onClick={handleBuyTickets}
                  >
                    Buy Tickets
                  </button>
                  <button className="md-iconBtn" type="button" aria-label="Add to favorites">
                    <Heart size={18} />
                  </button>
                </div>

              </div>
            </section>

            <section className="md-cast">
              <h3 className="md-castTitle">Your Favorite Cast</h3>
              <div className="md-castStrip">
                {cast.length ? (
                  cast.map((credit, idx) => {
                    const person = credit?.person || credit;
                    const avatar = person?.photo || person?.image || person?.avatar;
                    return (
                      <button
                        type="button"
                        className="md-castItem md-castBtn"
                        key={`${person.fullName || person.name || "cast"}-${idx}`}
                        onClick={() => openPerson(credit)}
                      >
                      <div className="md-castAvatar">
                        {avatar ? (
                          <img src={avatar} alt={person.fullName || person.name || "Cast"} />
                        ) : (
                          <div className="md-avatarPlaceholder">No photo</div>
                        )}
                      </div>
                        <div className="md-castName">{person.fullName || person.name || "Actor"}</div>
                        {credit?.characterName || credit?.roleName || person?.role ? (
                          <div className="md-castRole">
                            {credit?.characterName || credit?.roleName || person?.role}
                          </div>
                        ) : null}
                      </button>
                    );
                  })
                ) : (
                  <div className="md-empty">No cast details yet.</div>
                )}
              </div>
            </section>

            <section className="md-section">
              <h3 className="md-sectionTitle">Crew</h3>
              <div className="md-peopleRow">
                {crew.length ? (
                  crew.map((credit, idx) => (
                    <Person
                      key={`${credit?.person?.fullName || credit?.name || "crew"}-${idx}`}
                      name={credit?.person?.fullName || credit?.name}
                      role={
                        credit?.jobTitle ||
                        credit?.department ||
                        credit?.roleName ||
                        credit?.role
                      }
                      photo={credit?.person?.photo || credit?.photo}
                      onSelect={() => openPerson(credit)}
                    />
                  ))
                ) : (
                  <div className="md-empty">No crew details yet.</div>
                )}
              </div>
            </section>

            <section className="md-section">
              <div className="md-reviewHeader">
                <h3 className="md-sectionTitle">Reviews</h3>
                <div className="md-reviewSummary">
                  {ratingValue} / 5 {reviewCount ? `(${reviewCount})` : ""}
                </div>
              </div>

              <div className="md-reviewForm">
                {currentUser ? (
                  <div className="md-reviewFormFields">
                    <div className="md-starRow">
                      {Array.from({ length: 5 }).map((_, index) => {
                        const value = index + 1;
                        const active = value <= reviewRating;
                        return (
                          <button
                            key={`rate-${value}`}
                            type="button"
                            className={`md-starBtn ${active ? "active" : ""}`}
                            onClick={() => setReviewRating(value)}
                            aria-label={`Rate ${value} star${value > 1 ? "s" : ""}`}
                          >
                            <Star
                              className="md-starIcon"
                              aria-hidden="true"
                              size={40}
                              fill={active ? "currentColor" : "none"}
                            />
                          </button>
                        );
                      })}
                    </div>
                    <textarea
                      className="md-reviewTextarea"
                      rows="3"
                      value={reviewComment}
                      onChange={(event) => setReviewComment(event.target.value)}
                      placeholder="Share your thoughts about the movie."
                    />
                    <div className="md-reviewActions">
                      <button type="button" className="md-btn md-btnPrimary" onClick={handleReviewSubmit}>
                        {editingReviewId ? "Update Review" : "Submit Review"}
                      </button>
                      {editingReviewId ? (
                        <button
                          type="button"
                          className="md-btn md-btnGhost"
                          onClick={() => {
                            setEditingReviewId(null);
                            setReviewComment("");
                            setReviewRating(0);
                            setReviewStatus("");
                          }}
                        >
                          Cancel
                        </button>
                      ) : null}
                      {reviewStatus ? <span className="md-reviewStatus">{reviewStatus}</span> : null}
                    </div>
                  </div>
                ) : (
                  <div className="md-reviewLogin">
                    <span>Please log in to submit a review.</span>
                    <button type="button" className="md-btn md-btnPrimary" onClick={() => navigate("/login")}>
                      Login
                    </button>
                  </div>
                )}
              </div>

              <div className="md-reviewsRow">
                {reviews.length ? (
                  reviews.map((review, idx) => (
                    <Review
                      key={`${review.id || review.userId || "review"}-${idx}`}
                      userName={review.userName || review.user || "Anonymous"}
                      userImage={review.userImage}
                      rating={review.rating}
                      comment={review.comment || review.text}
                      createdAt={review.createdAt}
                      canManage={
                        Boolean(currentUser?.id) &&
                        String(review?.userId || "") === String(currentUser?.id || "")
                      }
                      onEdit={() => handleReviewEdit(review)}
                      onDelete={() => handleReviewDelete(review)}
                    />
                  ))
                ) : (
                  <div className="md-empty">No reviews yet.</div>
                )}
              </div>
            </section>

            {similarMovies.length ? (
              <section className="md-section md-likeSection">
                <div className="md-likeHead">
                  <h3 className="md-sectionTitle">You might also like</h3>
                  <button className="md-link" type="button" onClick={() => navigate("/movies")}>
                    View All
                  </button>
                </div>
                <div className="ns-grid md-likeGrid">
                  {similarMovies.slice(0, 3).map((item) => (
                    <SimilarCard
                      key={item._id || item.id || item.title}
                      movie={item}
                      onSelect={() =>
                        navigate(
                          `/movie/${item?.slug || item?._id || item?.id || encodeURIComponent(item?.title || item?.name || "")}`
                        )
                      }
                    />
                  ))}
                </div>
              </section>
            ) : null}
          </>
        )}
      </div>
      {isTrailerOpen ? (
        <div className="md-trailerModal" role="dialog" aria-modal="true">
          <div className={`md-trailerCard ${hasMultipleTrailers ? "md-trailerCardMulti" : ""}`}>
            <button
              className="md-trailerClose"
              type="button"
              onClick={closeTrailer}
              aria-label="Close trailer"
            >
              ×
            </button>
            <div className={`md-trailerBody ${hasMultipleTrailers ? "md-trailerBodyMulti" : ""}`}>
              <div className="md-trailerMain">
                <div className="md-trailerFrame">
                  <iframe
                    src={toEmbedUrl(currentTrailer)}
                    title="Trailer"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                    allowFullScreen
                  />
                </div>
              </div>
              {hasMultipleTrailers ? (
                <aside className="md-trailerRail" aria-label="Trailers list">
                  {trailerUrls.map((url, index) => {
                    const preview = buildTrailerPreview(url, title, index);
                    const active = url === currentTrailer;
                    return (
                      <button
                        key={`trailer-choice-${index + 1}`}
                        type="button"
                        className={`md-trailerItem ${active ? "active" : ""}`}
                        onClick={() => setCurrentTrailer(url)}
                      >
                        <span className="md-trailerItemThumbWrap">
                          <img
                            src={preview.thumbnail}
                            alt={preview.title}
                            className="md-trailerItemThumb"
                            loading="lazy"
                          />
                          <span className="md-trailerItemPlay">
                            <Play size={14} />
                          </span>
                        </span>
                        <span className="md-trailerItemInfo">
                          <span className="md-trailerItemTitle">{preview.title}</span>
                          <span className="md-trailerItemMeta">Trailer {index + 1}</span>
                        </span>
                      </button>
                    );
                  })}
                </aside>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
      {personLoading || selectedPerson || personError ? (
        <div
          className="md-personModal"
          role="dialog"
          aria-modal="true"
          onClick={closePerson}
        >
          <div className="md-personCard" onClick={(event) => event.stopPropagation()}>
            <button
              type="button"
              className="md-personClose"
              onClick={closePerson}
              aria-label="Close person details"
            >
              x
            </button>
            {personLoading ? (
              <div className="md-personLoading">Loading person details...</div>
            ) : personError ? (
              <div className="md-personError">{personError}</div>
            ) : selectedPerson ? (
              <PersonModalContent
                person={selectedPerson}
                selectedCredit={selectedCredit}
                currentMovieId={activeMovie?.id}
                onSelectMovie={(credit) => {
                  const key = credit?.movieSlug || credit?.movieId;
                  if (!key) return;
                  closePerson();
                  navigate(`/movie/${encodeURIComponent(key)}`);
                }}
              />
            ) : null}
          </div>
        </div>
      ) : null}
      <AdultWarningModal
        open={adultConfirmOpen}
        onCancel={() => setAdultConfirmOpen(false)}
        onConfirm={() => {
          setAdultConfirmOpen(false);
          navigateToSchedule();
        }}
      />
    </div>
  );
}

function safeUseAppContext() {
  try {
    return useAppContext?.();
  } catch {
    return null;
  }
}

function getStoredUser() {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem("user") || localStorage.getItem("user");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function toText(value) {
  if (!value) return "";
  if (Array.isArray(value)) return value.filter(Boolean).join(", ");
  return String(value).trim();
}

function getInitials(value) {
  const text = String(value || "").trim();
  if (!text) return "?";
  const parts = text
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2);
  if (!parts.length) return "?";
  return parts.map((part) => part.charAt(0).toUpperCase()).join("");
}

function resolveCredits(movie, targetRoleType) {
  const roleType = String(targetRoleType || "").toUpperCase();
  const directList = roleType === "CAST" ? movie?.cast : movie?.crew;
  if (Array.isArray(directList) && directList.length > 0) {
    return directList.map(normalizeCreditShape);
  }

  const credits = Array.isArray(movie?.credits) ? movie.credits : [];
  if (!credits.length) return [];

  return credits
    .filter((credit) => {
      const creditType = String(
        credit?.roleType ||
          credit?.role_type ||
          credit?.creditType ||
          ""
      ).toUpperCase();
      return creditType === roleType;
    })
    .map(normalizeCreditShape);
}

function normalizeCreditShape(credit) {
  const person = credit?.person || {};
  const personName = person?.fullName || person?.full_name || person?.name || "";
  const personPhoto =
    person?.photo || person?.photo_url || person?.photoUrl || credit?.photo || credit?.photo_url || credit?.photoUrl || "";

  return {
    ...credit,
    roleType:
      credit?.roleType ||
      credit?.role_type ||
      credit?.creditType ||
      "",
    characterName:
      credit?.characterName ||
      credit?.character_name ||
      credit?.roleName ||
      "",
    jobTitle:
      credit?.jobTitle ||
      credit?.job_title ||
      credit?.department ||
      "",
    roleName:
      credit?.roleName ||
      credit?.characterName ||
      credit?.character_name ||
      credit?.jobTitle ||
      credit?.job_title ||
      credit?.department ||
      "",
    person: {
      ...person,
      fullName: personName,
      name: person?.name || personName,
      photo: personPhoto,
      photoUrl: person?.photoUrl || person?.photo_url || personPhoto,
    },
  };
}

function resolveReviews(movie) {
  if (!Array.isArray(movie?.reviews)) return [];
  return movie.reviews.map((review) => ({
    ...review,
    userId: review?.userId || review?.user_id || review?.user || null,
    userName:
      review?.userName ||
      review?.user_name ||
      review?.user ||
      "Anonymous",
    userImage:
      review?.userImage ||
      review?.user_image ||
      review?.profileImage ||
      review?.profile_image ||
      review?.user_profile_image ||
      review?.avatar ||
      "",
    createdAt:
      review?.createdAt ||
      review?.created_at ||
      review?.review_date ||
      null,
  }));
}

function formatDateLabel(value) {
  if (!value) return "";
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) {
    return date.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  }
  return String(value);
}

function formatReviewDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) {
    return date.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  }
  return String(value);
}

function buildMetaLine(movie) {
  const language = toText(movie?.language || movie?.lang);
  const genre = Array.isArray(movie?.genres)
    ? movie.genres.map((g) => g?.name).filter(Boolean).join(", ")
    : toText(movie?.genre || movie?.category || movie?.type || movie?.genres);
  const parts = [language, genre].filter(Boolean);
  return parts.length ? parts.join(" | ") : "";
}

function formatRating(value) {
  if (value === null || value === undefined) return "";
  const num = Number(value);
  if (Number.isFinite(num)) {
    return num.toFixed(1);
  }
  return "";
}

function formatDuration(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number" && Number.isFinite(value)) {
    const hours = Math.floor(value / 60);
    const minutes = Math.round(value % 60);
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  }

  const text = String(value).trim();
  if (!text) return "";
  const numeric = Number(text);
  if (Number.isFinite(numeric)) {
    return formatDuration(numeric);
  }
  return text;
}

function formatYear(value) {
  if (!value) return "";
  if (typeof value === "number") return String(value);
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) {
    return String(date.getFullYear());
  }
  const text = String(value).trim();
  const match = text.match(/(19|20)\d{2}/);
  return match ? match[0] : text;
}

function getDirectorLabel(movie, crew) {
  const direct = toText(movie?.director || movie?.directors);
  if (direct) return direct;
  if (!Array.isArray(crew)) return "";
  const match = crew.find((credit) => {
    const label = String(
      credit?.jobTitle ||
        credit?.department ||
        credit?.roleName ||
        credit?.role ||
        ""
    ).toLowerCase();
    return label.includes("director");
  });
  return (
    match?.person?.fullName ||
    match?.person?.name ||
    match?.name ||
    ""
  );
}

function getCastLabel(cast) {
  if (!Array.isArray(cast)) return "";
  return cast
    .map((credit) => credit?.person?.fullName || credit?.person?.name || credit?.name)
    .filter(Boolean)
    .slice(0, 4)
    .join(", ");
}

function getTrailerLang(language) {
  if (!language) return "ENG";
  const first = String(language).split(/[,\s]/)[0];
  if (!first) return "ENG";
  return first.slice(0, 3).toUpperCase();
}

function resolveTrailerUrl(movie) {
  const trailers = resolveTrailerUrls(movie);
  return trailers[0] || "";
}

function resolveTrailerUrls(movie) {
  if (!movie) return [];
  const fromList = Array.isArray(movie?.trailerUrls)
    ? movie.trailerUrls
    : Array.isArray(movie?.trailer_urls)
      ? movie.trailer_urls
      : [];
  const single =
    movie.trailerUrl ||
    movie.trailer_url ||
    movie.trailer ||
    movie.videoUrl ||
    movie.youtubeUrl ||
    movie.youtube ||
    movie.trailer_link ||
    movie.trailerLink ||
    movie.promoUrl;

  const normalized = [];
  for (const value of [...fromList, single]) {
    const url = typeof value === "string"
      ? value.trim()
      : value && typeof value === "object"
        ? String(value.url || value.link || "").trim()
        : "";
    if (!url || normalized.includes(url)) continue;
    normalized.push(url);
  }
  return normalized;
}

function toEmbedUrl(url) {
  if (!url) return "";
  const id = extractYoutubeId(url);
  if (id) return `https://www.youtube.com/embed/${id}?rel=0`;
  return url;
}

function extractYoutubeId(url) {
  if (!url) return "";
  try {
    const match = url.match(/(?:v=)([0-9A-Za-z_-]{11})(?:[&?]|$)\s*/);
    const shortMatch = url.match(/youtu\.be\/([0-9A-Za-z_-]{11})/);
    const match2 = url.match(/\/([0-9A-Za-z_-]{11})(?:\?|$)/);
    const id = (match && match[1]) || (shortMatch && shortMatch[1]) || (match2 && match2[1]);
    if (id) return id;
  } catch {}
  return "";
}

function buildTrailerPreview(url, movieTitle, index) {
  const id = extractYoutubeId(url);
  const fallbackTitle = `${movieTitle || "Movie"} Trailer ${index + 1}`;
  const thumbnail = id
    ? `https://img.youtube.com/vi/${id}/mqdefault.jpg`
    : "https://img.youtube.com/vi/dQw4w9WgXcQ/mqdefault.jpg";
  return {
    title: fallbackTitle,
    thumbnail,
  };
}

function Person({ name, role, photo, onSelect }) {
  return (
    <button type="button" className="md-person md-personBtn" onClick={onSelect}>
      <div className="md-avatar">
        {photo ? (
          <img src={photo} alt={name || "Person"} />
        ) : (
          <div className="md-avatarPlaceholder">{getInitials(name)}</div>
        )}
      </div>
      <p className="md-personName">{name}</p>
      {role ? <p className="md-personRole">{role}</p> : null}
    </button>
  );
}

function Review({ userName, userImage, rating, comment, createdAt, canManage, onEdit, onDelete }) {
  const stars = Array.from({ length: 5 }).map((_, index) => {
    const value = index + 1;
    const active = value <= Number(rating || 0);
    return (
      <Star key={`star-${value}`} size={14} fill={active ? "currentColor" : "none"} />
    );
  });
  return (
    <div className="md-review">
      <div className="md-reviewHead">
        <div className="md-reviewAvatar">
          {userImage ? (
            <img src={userImage} alt={userName || "Reviewer"} />
          ) : (
            <span>{getInitials(userName)}</span>
          )}
        </div>
        <div>
          <p className="md-reviewName">{userName}</p>
          {createdAt ? (
            <p className="md-reviewDate">{formatReviewDate(createdAt)}</p>
          ) : null}
        </div>
        {canManage ? (
          <div className="d-flex gap-2 ms-auto me-2">
            <button type="button" className="md-link" onClick={onEdit}>
              Edit
            </button>
            <button type="button" className="md-link" onClick={onDelete}>
              Delete
            </button>
          </div>
        ) : null}
        <div className="md-reviewRating">{stars}</div>
      </div>
      {comment ? <p className="md-reviewText">{comment}</p> : null}
    </div>
  );
}

function PersonModalContent({ person, selectedCredit, currentMovieId, onSelectMovie }) {
  const filmography = Array.isArray(person?.filmography) ? person.filmography : [];
  const otherMovies = currentMovieId
    ? filmography.filter((credit) => String(credit?.movieId) !== String(currentMovieId))
    : filmography;
  const displayFilmography = otherMovies.length ? otherMovies : filmography;
  const name = person?.fullName || person?.name || "Person";
  const metaParts = [];
  if (person?.nationality) metaParts.push(person.nationality);
  if (person?.dateOfBirth) metaParts.push(formatDateLabel(person.dateOfBirth));
  const metaLine = metaParts.filter(Boolean).join(" | ");
  const roleLabel =
    selectedCredit?.roleType === "CAST"
      ? selectedCredit?.characterName
      : selectedCredit?.jobTitle || selectedCredit?.characterName;
  const socials = [
    { label: "Instagram", url: person?.instagram },
    { label: "IMDb", url: person?.imdb },
    { label: "Facebook", url: person?.facebook },
  ].filter((item) => item.url);

  return (
    <div className="md-personBody">
      <div className="md-personHeader">
        <div className="md-personPhoto">
          {person?.photo ? (
            <img src={person.photo} alt={name} />
          ) : (
            <div className="md-personPlaceholder">No photo</div>
          )}
        </div>
        <div>
          <h3 className="md-personName">{name}</h3>
          {metaLine ? <div className="md-personMeta">{metaLine}</div> : null}
          {roleLabel ? <div className="md-personMeta">Role: {roleLabel}</div> : null}
          {person?.bio ? <p className="md-personBio">{person.bio}</p> : null}
          {socials.length ? (
            <div className="md-personSocials">
              {socials.map((link) => (
                <a
                  key={link.label}
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {link.label}
                </a>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      <div className="md-personSectionTitle">Filmography</div>
      {displayFilmography.length ? (
        <div className="md-filmography">
          {displayFilmography.map((credit, idx) => {
            const poster = credit?.posterImage || credit?.bannerImage;
            const label =
              credit?.characterName ||
              credit?.jobTitle ||
              credit?.roleName ||
              credit?.department ||
              credit?.creditType;
            return (
              <button
                key={`${credit?.movieId || credit?.movieSlug || "film"}-${idx}`}
                type="button"
                className="md-filmCard"
                onClick={() => onSelectMovie?.(credit)}
              >
                <div className="md-filmPoster">
                  {poster ? (
                    <img src={poster} alt={credit?.movieTitle || "Movie"} />
                  ) : (
                    <div className="md-filmPlaceholder">No image</div>
                  )}
                </div>
                <div className="md-filmInfo">
                  <div className="md-filmTitle">{credit?.movieTitle || "Movie"}</div>
                  {label ? <div className="md-filmMeta">{label}</div> : null}
                </div>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="md-empty">No filmography available.</div>
      )}
    </div>
  );
}

function SimilarCard({ movie, onSelect }) {
  const title = movie?.title || movie?.name || "Movie Name";
  const poster =
    movie?.posterImage || movie?.poster || movie?.posterUrl || movie?.image || "";
  const dateLabel =
    formatDateLabel(movie?.releaseDate || movie?.date || movie?.showDate || movie?.premiere) ||
    "";
  const ratingLabel =
    toText(movie?.censor || movie?.rating || movie?.certificate || movie?.classification) || "NR";
  const metaLine = buildMetaLine(movie);
  const badgeClass = isAdultRating(ratingLabel) ? "ns-cardBadge ns-cardBadgeAdult" : "ns-cardBadge";

  const handleKeyDown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect?.();
    }
  };

  return (
    <div
      className="ns-card"
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={handleKeyDown}
    >
      <div className="ns-cardPoster">
        {poster ? <img src={poster} alt={title} /> : <div className="md-posterPlaceholder">No poster</div>}
        <div className={badgeClass}>{ratingLabel}</div>
      </div>

      <div className="ns-cardInfo">
        <div className="ns-cardTitle">{title}</div>
        {metaLine ? <div className="ns-cardMeta">{metaLine}</div> : null}
        {dateLabel ? <div className="ns-cardMeta">{dateLabel}</div> : null}
      </div>
    </div>
  );
}
