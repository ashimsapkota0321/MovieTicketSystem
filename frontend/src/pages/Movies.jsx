import React, { useEffect, useMemo, useState } from "react";
import "../css/home.css";
import { useLocation, useNavigate } from "react-router-dom";
import { Clock3, Film } from "lucide-react";
import { useAppContext } from "../context/Appcontext";
import HeroSlider from "../components/HeroSlider";
import NowShowingCard from "../components/NowShowingCard";
import { getComingSoon, getNowShowing, resolveMoviesByShowListing } from "../lib/showUtils";

export default function Movies() {
  const navigate = useNavigate();
  const location = useLocation();
  const ctx = safeUseAppContext();
  const movies = ctx?.movies ?? [];
  const showtimes = ctx?.showtimes ?? [];
  const initialTab =
    location?.state?.filter === "soon" || location?.hash === "#coming-soon" ? "soon" : "now";
  const [activeTab, setActiveTab] = useState(initialTab);
  const hideTabs = Boolean(location?.state?.hideTabs);

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

  // Filter movies to only those with active shows
  const hasActiveShowtimes = moviesWithActiveShows.size > 0;

  const moviesWithShows = useMemo(() => {
    if (!hasActiveShowtimes) return movies;
    return movies.filter((movie) => {
      const id = String(movie?.id || "").trim();
      return moviesWithActiveShows.has(id);
    });
  }, [movies, moviesWithActiveShows, hasActiveShowtimes]);

  const showBuckets = useMemo(
    () => resolveMoviesByShowListing(moviesWithShows, showtimes),
    [moviesWithShows, showtimes]
  );
  const nowShowing = useMemo(() => {
    if (!hasActiveShowtimes) return getNowShowing(moviesWithShows);
    return showBuckets.nowShowing;
  }, [showBuckets, moviesWithShows, hasActiveShowtimes]);
  const comingSoon = useMemo(() => {
    if (!hasActiveShowtimes) return getComingSoon(moviesWithShows);
    return showBuckets.comingSoon;
  }, [showBuckets, moviesWithShows, hasActiveShowtimes]);
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
      <HeroSlider page="movies" />
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
              {nowShowing.length ? (
                nowShowing.map((movie) => (
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
                <div className="text-muted">No now showing shows for this location.</div>
              )}
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
                  <NowShowingCard
                    key={movie._id || movie.id || movie.title}
                    movie={movie}
                    onBuy={() =>
                      navigate(
                        `/movie/${movie?._id || movie?.id || encodeURIComponent(movie?.title || movie?.name || "")}`,
                        { state: { movie, variant: "soon" } }
                      )
                    }
                  />
                ))
              ) : (
                <div className="text-muted">No coming soon shows for this location.</div>
              )}
            </div>
          </div>
        </section>
      ) : null}
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
