import React, { useEffect, useMemo, useState } from "react";
import "../css/home.css";
import { useLocation, useNavigate } from "react-router-dom";
import { Clock3, Film } from "lucide-react";
import { useAppContext } from "../context/Appcontext";
import BodyHero from "../components/BodyHero";
import kumari from "../images/kumari.jpg";
import gharjwai from "../images/gharjwai.jpg";
import balidan from "../images/balidan.jpg";
import degreemaila from "../images/degreemaila.jpg";
import avengers from "../images/avengers.jpg";
import background from "../images/kumari.jpg";
import Tiba from "../images/Tiba.jpg";
import aama from "../images/aama.png";

export default function Movies() {
  const navigate = useNavigate();
  const location = useLocation();
  const ctx = safeUseAppContext();
  const movies = ctx?.movies ?? ctx?.shows ?? fallbackShows;
  const initialTab =
    location?.state?.filter === "soon" || location?.hash === "#coming-soon" ? "soon" : "now";
  const [activeTab, setActiveTab] = useState(initialTab);
  const hideTabs = Boolean(location?.state?.hideTabs);

  const nowShowing = useMemo(() => getNowShowing(movies), [movies]);
  const comingSoon = useMemo(() => getComingSoon(movies), [movies]);
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

  const heroTarget = nowShowing?.[0];
  const handleHeroBuy = () => {
    if (heroTarget?._id || heroTarget?.id || heroTarget?.title || heroTarget?.name) {
      navigate(
        `/movie/${heroTarget?._id || heroTarget?.id || encodeURIComponent(heroTarget?.title || heroTarget?.name || "")}/schedule`
      );
      return;
    }
    navigate("/movies");
  };

  useEffect(() => {
    if (location?.state?.filter) {
      setActiveTab(location.state.filter === "soon" ? "soon" : "now");
      return;
    }
    if (location?.hash === "#coming-soon") {
      setActiveTab("soon");
      return;
    }
    if (location?.hash === "#now-showing") {
      setActiveTab("now");
    }
  }, [location?.hash, location?.state?.filter]);

  const handleTab = (tab, targetId) => {
    setActiveTab(tab);
    if (!hideTabs) {
      const target = document.getElementById(targetId);
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  };

  return (
    <div className={`wf2-page movies-page ${hideTabs ? "movies-pageTabsHidden" : ""}`}>
      <BodyHero
        slides={heroSlides}
        interval={6000}
        badge="Now Showing"
        variant="full"
        cta={{ label: "Buy Ticket", onClick: handleHeroBuy }}
      />
      {!hideTabs ? (
        <section className="wf2-container wf2-section movies-tabs">
          <div className="wf2-constrained">
            <div className="movies-tabBar">
              <button
                type="button"
                className={`movies-tab ${activeTab === "now" ? "movies-tabActive" : ""}`}
                onClick={() => handleTab("now", "now-showing")}
              >
                <Film size={18} className="movies-tabIcon movies-tabIconNow" />
                <span>Now Showing</span>
              </button>
              <span className="movies-tabDivider">|</span>
              <button
                type="button"
                className={`movies-tab ${activeTab === "soon" ? "movies-tabActive" : ""}`}
                onClick={() => handleTab("soon", "coming-soon")}
              >
                <Clock3 size={18} className="movies-tabIcon movies-tabIconSoon" />
                <span>Coming Soon</span>
              </button>
            </div>
          </div>
        </section>
      ) : null}

      {activeTab === "now" ? (
        <section className="wf2-container wf2-section movies-nowshowing" id="now-showing">
          <div className="wf2-constrained">
            <div className="ns-grid">
              {nowShowing.map((movie) => (
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
          </div>
        </section>
      ) : null}

      {activeTab === "soon" ? (
        <section className="wf2-container wf2-section movies-comingsoon" id="coming-soon">
          <div className="wf2-constrained">
            <div className="ns-grid">
              {comingSoon.length ? (
                comingSoon.map((movie) => (
                  <NowCard
                    key={movie._id || movie.id || movie.title}
                    movie={movie}
                    onBuy={() =>
                      navigate(
                        `/movie/${movie?._id || movie?.id || encodeURIComponent(movie?.title || movie?.name || "")}`,
                        { state: { variant: "soon" } }
                      )
                    }
                  />
                ))
              ) : (
                fallbackShows.slice(0, 6).map((movie) => (
                  <NowCard
                    key={movie._id || movie.id || movie.title}
                    movie={movie}
                    onBuy={() =>
                      navigate(
                        `/movie/${movie?._id || movie?.id || encodeURIComponent(movie?.title || movie?.name || "")}`,
                        { state: { variant: "soon" } }
                      )
                    }
                  />
                ))
              )}
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function NowCard({ movie, onBuy }) {
  const title = movie?.title || movie?.name || "Movie Name";
  const poster =
    movie?.bannerImage || movie?.poster || movie?.posterUrl || movie?.image || gharjwai;
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

function safeUseAppContext() {
  try {
    return useAppContext?.();
  } catch {
    return null;
  }
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

function getNowShowing(items) {
  if (!Array.isArray(items)) return [];
  const filtered = items.filter((item) =>
    isNowShowingStatus(item?.listingStatus || item?.status)
  );
  return filtered.length ? filtered : items.filter(Boolean).slice(0, 6);
}

function getComingSoon(items) {
  if (!Array.isArray(items)) return [];
  const filtered = items.filter((item) =>
    isComingSoonStatus(item?.listingStatus || item?.status)
  );
  return filtered.length ? filtered : items.filter(Boolean).slice(6, 12);
}

function isNowShowingStatus(status) {
  const value = String(status || "").toLowerCase();
  return value.includes("now") || value.includes("showing");
}

function isComingSoonStatus(status) {
  const value = String(status || "").toLowerCase();
  return value.includes("coming") || value.includes("soon") || value.includes("premiere");
}

const fallbackShows = [
  { _id: "1", title: "Gharjwai", poster: gharjwai },
  { _id: "2", title: "Balidan", poster: balidan },
  { _id: "3", title: "Degree Maila", poster: degreemaila },
  { _id: "4", title: "Avengers", poster: avengers },
  { _id: "5", title: "Gharjwai 2", poster: gharjwai },
  { _id: "6", title: "Balidan 2", poster: balidan },
  { _id: "7", title: "Degree Maila 2", poster: degreemaila },
  { _id: "8", title: "Avengers 2", poster: avengers },
  { _id: "9", title: "Gharjwai 3", poster: gharjwai },
  { _id: "10", title: "Balidan 3", poster: balidan },
  { _id: "11", title: "Degree Maila 3", poster: degreemaila },
  { _id: "12", title: "Avengers 3", poster: avengers },
];
