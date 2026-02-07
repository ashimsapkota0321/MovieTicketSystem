import React, { useMemo } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Heart, Play, Star } from "lucide-react";

import "../css/movieDetails.css";
import "../css/home.css";
import { useAppContext } from "../context/Appcontext";

import gharjwai from "../images/gharjwai.jpg";
import balidan from "../images/balidan.jpg";
import degreemaila from "../images/degreemaila.jpg";
import avengers from "../images/avengers.jpg";

export default function MovieDetails() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();

  const ctx = safeUseAppContext();
  const shows = ctx?.shows ?? fallbackShows;

  const movie = useMemo(() => findMovie(shows, id) ?? fallbackShows[0], [shows, id]);
  const isComingSoon = Boolean(location?.state?.variant === "soon" || location?.state?.isComingSoon);

  const title = movie?.title || movie?.name || "Movie Title";
  const poster = movie?.poster || movie?.posterUrl || movie?.image || gharjwai;
  const language = toText(movie?.language || movie?.lang) || "English";
  const ratingValue = formatRating(movie?.rating || movie?.imdbRating || movie?.score) || "7.5";
  const description =
    toText(movie?.description || movie?.overview || movie?.synopsis) ||
    "After cracking the biggest case in the city, two rookie cops find themselves on the trail of a new mystery that tests their growing partnership.";
  const duration = formatDuration(movie?.duration || movie?.runtime);
  const genres = toText(movie?.genres || movie?.genre || movie?.category);
  const year = formatYear(movie?.year || movie?.releaseDate || movie?.premiere);
  const metaParts = [duration, genres, year].filter(Boolean);
  const metaLine =
    metaParts.length > 0
      ? metaParts.join(" | ")
      : "1h 47m | Animation, Family, Comedy, Adventure, Mystery | 2025";

  const cast = useMemo(() => {
    if (Array.isArray(movie?.cast) && movie.cast.length > 0) return movie.cast;
    return defaultCast;
  }, [movie]);

  const crew = useMemo(() => {
    if (Array.isArray(movie?.crew) && movie.crew.length > 0) return movie.crew;
    return defaultCrew;
  }, [movie]);

  const reviews = useMemo(() => {
    if (Array.isArray(movie?.reviews) && movie.reviews.length > 0) return movie.reviews;
    return defaultReviews;
  }, [movie]);

  const releaseLabel = formatDateLabel(
    movie?.releaseDate || movie?.premiere || movie?.showDate || movie?.date
  );
  const releaseValue = releaseLabel || "TBA";
  const ageRating =
    toText(movie?.certificate || movie?.classification || movie?.censor || movie?.ageRating) || "PG";
  const runtimeLabel = formatDuration(movie?.duration || movie?.runtime) || "TBA";
  const yearLabel = formatYear(movie?.year || movie?.releaseDate || movie?.premiere) || "TBA";
  const genresLabel = genres || "Drama";
  const originalTitle = toText(movie?.originalTitle) || title;
  const directorLabel = getDirectorLabel(movie, crew) || "TBA";
  const castLabel = getCastLabel(cast) || "TBA";
  const trailerLang = getTrailerLang(language);
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
        <div className="md-soonTrailer">
          <span className="md-soonPlay">
            <Play size={12} />
          </span>
          <span className="md-soonTrailerText">{trailerLang}</span>
        </div>
      ),
    },
  ];

  return (
    <div className={`md-page ${isComingSoon ? "md-soonPage" : ""}`}>
      <div className="md-container">
        {isComingSoon ? (
          <div className="md-soonPanel">
            <section className="md-soonHero">
              <div className="md-soonPoster">
                <img src={poster} alt={title} />
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
                <img src={poster} alt={title} />
              </div>

              <div className="md-info">
                <div className="md-lang">{language}</div>
                <h1 className="md-title">{title}</h1>

                <div className="md-rating">
                  <Star size={16} />
                  <span>{ratingValue} User Rating</span>
                </div>

                <p className="md-desc">{description}</p>
                <div className="md-meta">{metaLine}</div>

                <div className="md-actions">
                  <button className="md-btn md-btnGhost" type="button">
                    <span className="md-btnIcon">
                      <Play size={14} />
                    </span>
                    Watch Trailer
                  </button>
                  <button
                    className="md-btn md-btnPrimary"
                    type="button"
                    onClick={() =>
                      navigate(`/movie/${id || movie?._id || movie?.id || encodeURIComponent(title)}/schedule`)
                    }
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
                {cast.map((person, idx) => {
                  const avatar = person?.image || person?.photo || person?.avatar;
                  return (
                    <div className="md-castItem" key={`${person.name || "cast"}-${idx}`}>
                      <div className="md-castAvatar">
                        {avatar ? <img src={avatar} alt={person.name || "Cast"} /> : null}
                      </div>
                      <div className="md-castName">{person.name || "Actor"}</div>
                      {person.role ? <div className="md-castRole">{person.role}</div> : null}
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="md-section">
              <h3 className="md-sectionTitle">Crew</h3>
              <div className="md-peopleRow">
                {crew.map((person, idx) => (
                  <Person key={`${person.name || "crew"}-${idx}`} name={person.name} role={person.role} />
                ))}
              </div>
            </section>

            <section className="md-section">
              <h3 className="md-sectionTitle">Top reviews</h3>
              <div className="md-reviewsRow">
                {reviews.map((review, idx) => (
                  <Review key={`${review.user || "review"}-${idx}`} user={review.user} text={review.text} />
                ))}
              </div>
            </section>

            <section className="md-section md-likeSection">
              <div className="md-likeHead">
                <h3 className="md-sectionTitle">You might also like</h3>
                <button className="md-link" type="button" onClick={() => navigate("/movies")}>
                  View All
                </button>
              </div>
              <div className="ns-grid md-likeGrid">
                {(shows?.slice?.(0, 3) ?? fallbackShows.slice(0, 3)).map((item) => (
                  <SimilarCard
                    key={item._id || item.id || item.title}
                    movie={item}
                    onSelect={() =>
                      navigate(
                        `/movie/${item?._id || item?.id || encodeURIComponent(item?.title || item?.name || "")}`
                      )
                    }
                  />
                ))}
              </div>
            </section>
          </>
        )}
      </div>
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

function findMovie(shows, id) {
  if (!shows || !id) return null;
  const decoded = safeDecode(id);

  const direct = shows.find((s) => `${s._id}` === id || `${s.id}` === id);
  if (direct) return direct;

  const byTitle = shows.find((s) => {
    const t = (s.title || s.name || "").trim();
    if (!t) return false;
    return t === decoded || encodeURIComponent(t) === id;
  });
  return byTitle || null;
}

function safeDecode(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function toText(value) {
  if (!value) return "";
  if (Array.isArray(value)) return value.filter(Boolean).join(", ");
  return String(value).trim();
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

function buildMetaLine(movie) {
  const language = toText(movie?.language || movie?.lang);
  const genre = toText(movie?.genre || movie?.category || movie?.type || movie?.genres);
  const parts = [language, genre].filter(Boolean);
  return parts.length ? parts.join(" | ") : "Nepali | Drama";
}

function isAdultRating(label) {
  const value = String(label || "").toLowerCase();
  return value.includes("adult") || value.includes("18");
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
  const match = crew.find((person) => String(person?.role || "").toLowerCase().includes("director"));
  return match?.name || "";
}

function getCastLabel(cast) {
  if (!Array.isArray(cast)) return "";
  return cast
    .map((person) => person?.name)
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

const fallbackShows = [
  { _id: "1", title: "Gharjwai", poster: gharjwai },
  { _id: "2", title: "Balidan", poster: balidan },
  { _id: "3", title: "Degree Maila", poster: degreemaila },
  { _id: "4", title: "Avengers", poster: avengers },
];

const defaultCast = [
  { name: "Ashish Sapkota" },
  { name: "Ashok Sapkota" },
  { name: "Ashim Sapkota" },
  { name: "Sajid Nadiadwala" },
  { name: "Ramesh Koirala" },
];

const defaultCrew = [
  { name: "Rajesh Hamal", role: "Director" },
  { name: "Nikhil Upreti", role: "Producer" },
  { name: "Shree Krishna Shrestha", role: "Writer" },
];

const defaultReviews = [
  {
    user: "Asim",
    text:
      "Lorem ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book.",
  },
  {
    user: "Asim",
    text:
      "Lorem ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book.",
  },
  {
    user: "Asim",
    text:
      "Lorem ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book.",
  },
];

function Person({ name, role }) {
  return (
    <div className="md-person">
      <div className="md-avatar" />
      <p className="md-personName">{name}</p>
      {role ? <p className="md-personRole">{role}</p> : null}
    </div>
  );
}

function Review({ user, text }) {
  return (
    <div className="md-review">
      <div className="md-reviewHead">
        <div className="md-reviewAvatar" />
        <div>
          <p className="md-reviewName">{user}</p>
        </div>
        <div className="md-reviewRating">
          <Star size={14} /> Rating
        </div>
      </div>
      <p className="md-reviewText">{text}</p>
    </div>
  );
}

function SimilarCard({ movie, onSelect }) {
  const title = movie?.title || movie?.name || "Movie Name";
  const poster = movie?.poster || movie?.posterUrl || movie?.image || gharjwai;
  const dateLabel =
    formatDateLabel(movie?.releaseDate || movie?.date || movie?.showDate || movie?.premiere) ||
    "13 Feb 2026";
  const ratingLabel =
    toText(movie?.censor || movie?.rating || movie?.certificate || movie?.classification) || "PG";
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
        <img src={poster} alt={title} />
        <div className={badgeClass}>{ratingLabel}</div>
      </div>

      <div className="ns-cardInfo">
        <div className="ns-cardTitle">{title}</div>
        <div className="ns-cardMeta">{metaLine}</div>
      </div>
    </div>
  );
}
