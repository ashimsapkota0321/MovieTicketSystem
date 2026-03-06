import React, { useEffect, useMemo, useState } from "react";
import "../css/home.css";
import { useLocation, useNavigate } from "react-router-dom";
import { Clock3, Film } from "lucide-react";
import { useAppContext } from "../context/Appcontext";
import HeroSlider from "../components/HeroSlider";
import NowShowingCard from "../components/NowShowingCard";
import { getComingSoon, getNowShowing } from "../lib/showUtils";
import gharjwai from "../images/gharjwai.jpg";
import balidan from "../images/balidan.jpg";
import degreemaila from "../images/degreemaila.jpg";
import avengers from "../images/avengers.jpg";

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
              {nowShowing.map((movie) => (
                <NowShowingCard
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
                  <NowShowingCard
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
                  <NowShowingCard
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

function safeUseAppContext() {
  try {
    return useAppContext?.();
  } catch {
    return null;
  }
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
