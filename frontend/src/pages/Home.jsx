import React, { useMemo, useState } from "react";
import "../css/home.css";
import { useNavigate } from "react-router-dom";
import { Film, Play } from "lucide-react";
import { useAppContext } from "../context/Appcontext";
import BodyHero from "../components/BodyHero";
import background from "../images/kumari.jpg";
import gharjwai from "../images/gharjwai.jpg";
import balidan from "../images/balidan.jpg";
import degreemaila from "../images/degreemaila.jpg";
import avengers from "../images/avengers.jpg";
import jerry from "../images/jerry.jpg";
import Tiba from "../images/Tiba.jpg";
import aama from "../images/aama.png"

export default function Home() {
  const navigate = useNavigate();

  const ctx = safeUseAppContext();
  const shows = ctx?.shows ?? fallbackShows;
  const nowShowing = useMemo(() => shows?.filter(Boolean).slice(0, 5), [shows]);
  const visibleShows = nowShowing.length ? nowShowing : fallbackShows;

  const heroSlides = useMemo(
    () => [
      {
        title: "Kumari",
        genre: "Romantic | Dramatic",
        year: "2018",
        duration: "2h 8m",
        desc:
          "Ramro Movie in Nepal, Actor: Rajesh Hamal, Nikhil Upreti, Late Shree Krishna Shrestha, Rekha Thapa etc.",
        bg: background,
      },
      {
        title: "Tiba",
        genre: "Action | Sci-Fi",
        year: "2021",
        duration: "3h 1m",
        desc:
          "The heroes assemble for a final stand that decides the fate of the universe.",
        bg: Tiba,
      },
      {
        title: "Aa Bata Aama",
        genre: "Emotional | Romantic",
        year: "2025",
        duration: "3h 1m",
        desc:
          "The heroes assemble for a final stand that decides the fate of the universe.",
        bg: aama,
      },
    ],
    []
  );



  const trailers = useMemo(
    () => [
      {
        image: gharjwai,
        url: "https://www.youtube.com/watch?v=1WajDWLXuVU",
        title: "Gharjwai Official Trailer",
        channel: "Mero Studio",
        views: "8.6m views",
        age: "1 month ago",
        duration: "16:23",
      },
      {
        image: balidan,
        url: "https://www.youtube.com/watch?v=ZtZSSgDDXrk",
        title: "Balidan Trailer",
        channel: "Nepal Cinema",
        views: "191k views",
        age: "20 hours ago",
        duration: "23:45",
      },
      {
        image: degreemaila,
        url: "https://www.youtube.com/watch?v=Sy5x1Nwm4mw",
        title: "Degree Maila 3 Teaser",
        channel: "The Nepali Comment",
        views: "49k views",
        age: "22 hours ago",
        duration: "12:34",
      },
      {
        image: avengers,
        url: "https://www.youtube.com/watch?v=6ZfuNTqbHE8",
        title: "Avengers: Endgame Official Trailer",
        channel: "Marvel Studio",
        views: "6.3m views",
        age: "2 weeks ago",
        duration: "1:30:13",
      },
      {
        image: jerry,
        url: "https://www.youtube.com/watch?v=BQrrJ-7ORDw&list=RDBQrrJ-7ORDw&start_radio=1",
        title: "Jerry On Top Trailer",
        channel: "Sourav Joshi Vlogs",
        views: "2.3m views",
        age: "9 hours ago",
        duration: "10:25",
      },
    ],
    []
  );

  const [currentTrailer, setCurrentTrailer] = useState(trailers[0]);
  const activeTrailer = currentTrailer || trailers[0];

  return (
    <div className="wf2-page">
      {/* ===== HERO ===== */}
      <BodyHero
        slides={heroSlides}
        interval={6000}
        badge="Now Showing"
        variant="full"
        cta={{ label: "Buy Ticket", onClick: () => navigate("/movies") }}
      />

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
              {visibleShows.map((movie) => (
                <NowCard
                  key={movie._id || movie.id || movie.title}
                  movie={movie}
                  onBuy={() =>
                    navigate(
                      `/movie/${movie?._id || movie?.id || encodeURIComponent(movie?.title || movie?.name || "")}`
                    )
                  }
                />
              ))}
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
        <section className="wf2-container wf2-section home-trailers">
          <div className="wf2-constrained">
            <div className="ns-head">
              <h3 className="ns-tab ns-tabActive">
                <Play size={18} />
                <span>Trailers</span>
              </h3>
            </div>

            <div className="wf2-trailerLayout">
              <div className="wf2-trailerPlayer">
                <div className="wf2-trailerMain">
                  <iframe
                    src={toEmbedUrl(activeTrailer?.url || trailers[0].url)}
                    title="Trailer"
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
                  {trailers.slice(0, 5).map((t, i) => (
                    <button
                      key={i}
                      className={`wf2-thumbBtn ${activeTrailer?.url === t.url ? "wf2-thumbActive" : ""}`}
                      onClick={() => setCurrentTrailer(t)}
                      aria-label={t.title || `Trailer ${i + 1}`}
                      type="button"
                    >
                      <div className="wf2-thumbMedia">
                        <img src={t.image} alt={t.title || `Trailer ${i + 1}`} loading="lazy" decoding="async" />
                        {t.duration ? <span className="wf2-thumbDuration">{t.duration}</span> : null}
                      </div>
                      <div className="wf2-thumbInfo">
                        <div className="wf2-thumbTitle">{t.title || `Trailer ${i + 1}`}</div>
                      </div>
                    </button>
                  ))}
                </div>
              </aside>
            </div>
          </div>
        </section>
      </section>

      {/* Footer removed to avoid duplicate — global Footer renders from Layout */}
    </div>
  );
}

/* ===== Now Showing Card ===== */
function NowCard({ movie, onBuy }) {
  const title = movie?.title || movie?.name || "Movie Name";
  const poster = movie?.poster || movie?.posterUrl || movie?.image || gharjwai;
  const dateLabel =
    formatDateLabel(movie?.releaseDate || movie?.date || movie?.showDate || movie?.premiere) || "13 Feb 2026";
  const ratingLabel =
    toText(movie?.censor || movie?.rating || movie?.certificate || movie?.classification) || "PG";
  const metaLine = buildMetaLine(movie);
  const badgeClass = isAdultRating(ratingLabel) ? "ns-cardBadge ns-cardBadgeAdult" : "ns-cardBadge";

  const handleKeyDown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onBuy?.();
    }
  };

  return (
    <div
      className="ns-card"
      role="button"
      tabIndex={0}
      onClick={onBuy}
      onKeyDown={handleKeyDown}
    >
      <div className="ns-cardPoster">
        <img src={poster} alt={title} loading="lazy" decoding="async" />
        <div className={badgeClass}>{ratingLabel}</div>
      </div>

      <div className="ns-cardInfo">
        <div className="ns-cardTitle">{title}</div>
        <div className="ns-cardMeta">{metaLine}</div>
      </div>
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

function toText(value) {
  if (!value) return "";
  if (Array.isArray(value)) return value.filter(Boolean).join(", ");
  return String(value);
}

function buildMetaLine(movie) {
  const language = toText(movie?.language || movie?.lang);
  const genre = toText(movie?.genre || movie?.category || movie?.type);
  const parts = [language, genre].filter(Boolean);
  return parts.length ? parts.join(" | ") : "Nepali | Drama";
}

function isAdultRating(label) {
  const value = String(label || "").toLowerCase();
  return value.includes("adult") || value.includes("18");
}

const fallbackShows = [
  { _id: "1", title: "Gharjwai", poster: gharjwai },
  { _id: "2", title: "Balidan", poster: balidan },
  { _id: "3", title: "Degree Maila", poster: degreemaila },
  { _id: "4", title: "Avengers", poster: avengers },
  { _id: "5", title: "Jerry: On Top", poster: jerry },
];
