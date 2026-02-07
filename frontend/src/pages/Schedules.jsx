import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import "../css/schedule.css";

import { useAppContext } from "../context/Appcontext";
import { getCinemaBySlug, getCinemaFallback, resolveCinemaSlug } from "../lib/cinemas";

import gharjwai from "../images/gharjwai.jpg";
import avengers from "../images/avengers.jpg";
import degreemaila from "../images/degreemaila.jpg";
import balidan from "../images/balidan.jpg";

const days = [
  { label: "Today", date: "Feb 5th", times: ["08:30 AM", "11:00 AM", "02:30 PM", "07:45 PM"] },
  { label: "Fri", date: "06.02", times: ["08:30 AM", "11:00 AM", "05:30 PM"] },
  { label: "Sat", date: "07.02" },
  { label: "Sun", date: "08.02" },
  { label: "Mon", date: "09.02" },
  { label: "Tue", date: "10.02" },
  { label: "Wed", date: "11.02" },
];

export default function Schedules() {
  const navigate = useNavigate();
  const { vendor } = useParams();
  const ctx = safeUseAppContext();
  const shows = ctx?.shows ?? [];
  const [currentTrailer, setCurrentTrailer] = useState("");
  const [isTrailerOpen, setTrailerOpen] = useState(false);

  const vendorSlug = useMemo(() => resolveCinemaSlug(vendor || ""), [vendor]);
  const selectedCinema = useMemo(() => getCinemaBySlug(vendorSlug), [vendorSlug]);

  const openTrailer = (url) => {
    if (!url) return;
    setCurrentTrailer(url);
    setTrailerOpen(true);
  };

  const closeTrailer = () => {
    setTrailerOpen(false);
  };

  const scheduleItems = useMemo(() => {
    const trailerUrls = [
      "https://www.youtube.com/watch?v=1WajDWLXuVU",
      "https://www.youtube.com/watch?v=ZtZSSgDDXrk",
      "https://www.youtube.com/watch?v=Sy5x1Nwm4mw",
      "https://www.youtube.com/watch?v=6ZfuNTqbHE8",
    ];
    const fallback = [
      {
        title: "Hami Teen Bhai",
        language: "Nepali",
        genre: "Action, Comedy",
        duration: "127 min",
        censor: "UA 13+",
        director: "Shive Regrin",
        desc:
          "A tender romantic drama about two young hearts brought together by fate. Set against Nepali cultural backdrop.",
        poster: gharjwai,
        cinema: "QFX Cinemas",
        trailerUrl: trailerUrls[0],
      },
      {
        title: "Avengers: The End Game",
        language: "English",
        genre: "Action, Sci-Fi",
        duration: "181 min",
        censor: "UA 13+",
        director: "Shive Regrin",
        desc:
          "The heroes assemble for a final stand. A visual spectacle with high stakes and emotional payoff.",
        poster: avengers,
        cinema: "Midtown Cinemas",
        trailerUrl: trailerUrls[1],
      },
      {
        title: "Spider-Man: No Way Home",
        language: "English",
        genre: "Action, Comedy",
        duration: "148 min",
        censor: "UA 13+",
        director: "Shive Regrin",
        desc:
          "Peter faces multiverse chaos as old foes return. A fast paced story with heart and humor.",
        poster: degreemaila,
        cinema: "FCube Cinemas",
        trailerUrl: trailerUrls[2],
      },
      {
        title: "Resham Filili",
        language: "Nepali",
        genre: "Comedy, Romance",
        duration: "125 min",
        censor: "UA 13+",
        director: "Shive Regrin",
        desc:
          "A playful ride through friendship and love, mixing humor with a grounded Nepali setting.",
        poster: balidan,
        cinema: "Big Movies",
        trailerUrl: trailerUrls[3],
      },
    ];

    const baseItems =
      !shows || shows.length === 0
        ? fallback.map((item, index) => ({
            ...item,
            cinemaRaw: item.cinema,
            index,
          }))
        : shows.slice(0, 4).map((show, index) => ({
            title: show?.title || show?.name || fallback[index]?.title,
            language: show?.language || fallback[index]?.language,
            genre: show?.genre || fallback[index]?.genre,
            duration: show?.duration || fallback[index]?.duration,
            censor: show?.censor || fallback[index]?.censor,
            director: show?.director || fallback[index]?.director,
            desc: show?.desc || fallback[index]?.desc,
            poster: show?.poster || show?.posterUrl || show?.image || fallback[index]?.poster,
            trailerUrl:
              show?.trailerUrl ||
              show?.trailer ||
              show?.videoUrl ||
              show?.youtubeUrl ||
              show?.youtube ||
              fallback[index]?.trailerUrl ||
              trailerUrls[index % trailerUrls.length],
            cinemaRaw:
              show?.cinema ||
              show?.theatre ||
              show?.vendor ||
              show?.hall ||
              show?.cinemaHall ||
              fallback[index]?.cinema,
            index,
          }));

    return baseItems.map(({ cinemaRaw, index, ...rest }) => {
      const fallbackCinema = vendorSlug ? getCinemaBySlug(vendorSlug) : getCinemaFallback(index);
      const cinemaSlug = resolveCinemaSlug(cinemaRaw) || fallbackCinema?.slug || "";
      const cinemaName =
        getCinemaBySlug(cinemaSlug)?.name || cinemaRaw || fallbackCinema?.name || "Cinema";
      return { ...rest, cinemaSlug, cinemaName };
    });
  }, [shows, vendorSlug]);

  const visibleItems = useMemo(() => {
    if (!vendorSlug) return scheduleItems;
    return scheduleItems.filter((item) => item.cinemaSlug === vendorSlug);
  }, [scheduleItems, vendorSlug]);

  return (
    <div className="schedule-page">
      <div className="schedule-wrap">
        <div className="schedule-crumb">
          {vendorSlug ? "Cinemas" : "Program"} &gt; {vendorSlug ? selectedCinema?.name || "Cinema" : "Showtimes"}
        </div>
        <div className="schedule-filters">
          <div className="schedule-filter">
            <span className="schedule-filterLabel">Period</span>
            <div className="schedule-pillGroup">
              <button className="schedule-pill schedule-pillActive" type="button">This Week</button>
              <button className="schedule-pill" type="button">Next Week</button>
            </div>
          </div>
          <div className="schedule-filter">
            <span className="schedule-filterLabel">Language</span>
            <select className="schedule-select">
              <option>All Language</option>
              <option>Nepali</option>
              <option>English</option>
            </select>
          </div>
        </div>

        <div className="schedule-list">
          {visibleItems.map((item, index) => (
            <div className="schedule-card" key={`${item.title}-${index}`}>
              <div className="schedule-left">
                <div className="schedule-posterWrap">
                  <div className="schedule-ribbon">Advance</div>
                  <div className="schedule-poster">
                    <img src={item.poster} alt={item.title} />
                  </div>
                </div>
              </div>

              <div className="schedule-middle">
                <h3 className="schedule-title">{item.title}</h3>
                <div className="schedule-badges">
                  <span className="schedule-badge">{item.censor}</span>
                  <span className="schedule-badge">{item.duration}</span>
                </div>
                <p className="schedule-desc">{item.desc}</p>
                <div className="schedule-lang">
                  <button
                    className="schedule-play"
                    type="button"
                    aria-label={`Play trailer for ${item.title}`}
                    onClick={() => openTrailer(item.trailerUrl)}
                  >
                    &gt;
                  </button>
                  <span>{item.language}</span>
                </div>
                <button className="schedule-infoBtn" type="button">Info</button>
              </div>

              <div className="schedule-right">
                <div className="schedule-rightTop">
                  <span className="schedule-rightLabel">{item.language.slice(0, 3).toUpperCase()}</span>
                </div>
                <div className="schedule-daysRow">
                  {days.map((day) => (
                    <div className="schedule-dayHead" key={`${item.title}-${day.label}-head`}>
                      {day.label}
                      <span>{day.date}</span>
                    </div>
                  ))}
                </div>
                <div className="schedule-timesRow">
                  {days.map((day) => (
                    <div className="schedule-dayTimes" key={`${item.title}-${day.label}-times`}>
                      {(day.times || []).map((time) => (
                        <button
                          className="schedule-time"
                          type="button"
                          key={`${day.label}-${time}`}
                          onClick={() => navigate("/booking")}
                        >
                          {time}
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
          {visibleItems.length === 0 ? (
            <div className="schedule-empty">
              No showtimes available for this cinema yet.
            </div>
          ) : null}
        </div>
      </div>

      {isTrailerOpen && (
        <div className="schedule-modal" role="dialog" aria-modal="true">
          <div className="schedule-modalContent">
            <button
              className="schedule-modalClose"
              type="button"
              onClick={closeTrailer}
              aria-label="Close trailer"
            >
              x
            </button>
            <div className="schedule-modalFrame">
              <iframe
                src={toEmbedUrl(currentTrailer)}
                title="Trailer"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                allowFullScreen
              />
            </div>
          </div>
        </div>
      )}
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
