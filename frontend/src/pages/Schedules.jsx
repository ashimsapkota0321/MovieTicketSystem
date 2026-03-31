import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import "../css/schedule.css";

import { useAppContext } from "../context/Appcontext";
import { getCinemaBySlug, getCinemaFallback, resolveCinemaSlug } from "../lib/cinemas";

export default function Schedules() {
  const navigate = useNavigate();
  const { vendor } = useParams();
  const ctx = safeUseAppContext();
  const movies = ctx?.movies ?? [];
  const showtimes = ctx?.showtimes ?? [];
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
    if (!Array.isArray(showtimes) || showtimes.length === 0) return [];

    const movieIndex = buildMovieIndex(movies);
    const grouped = new Map();

    showtimes.forEach((show) => {
      const vendorName = String(show.vendor || show.vendor_name || show.vendorName || show.cinema || "").trim();
      const showDate = String(show.date || show.show_date || show.showDate || "").trim();
      const showTime = String(show.start || show.start_time || show.startTime || "").trim();
      if (!vendorName || !showDate || !showTime) return;

      const movie = resolveMovieForShow(show, movieIndex);
      const movieTitle = movie?.title || movie?.name || show.movie || show.movie_title || "Movie";
      const movieKey = String(movie?.id || movie?._id || movieTitle).trim();
      const key = `${movieKey}__${vendorName.toLowerCase()}`;

      const group = grouped.get(key) || {
        movieId: movie?.id || movie?._id || show.movieId || show.movie_id || null,
        movieSlug: movie?.slug || show.movieSlug || show.movie_slug || null,
        title: movieTitle,
        language: movie?.language || movie?.lang || "Nepali",
        genre: movie?.genre || movie?.category || "",
        duration: movie?.duration || movie?.runtime || "",
        censor: movie?.censor || movie?.rating || "",
        director: movie?.director || "",
        desc: movie?.description || movie?.overview || movie?.synopsis || "",
        poster:
          show?.posterImage ||
          show?.poster_image ||
          show?.posterUrl ||
          show?.poster_url ||
          show?.poster ||
          movie?.posterImage ||
          movie?.poster_image ||
          movie?.poster ||
          movie?.posterUrl ||
          movie?.poster_url ||
          movie?.bannerImage ||
          movie?.image ||
          "",
        trailerUrl:
          movie?.trailerUrl ||
          movie?.trailer_url ||
          movie?.trailer ||
          movie?.videoUrl ||
          movie?.youtubeUrl ||
          movie?.youtube ||
          "",
        cinemaRaw: vendorName,
        dates: {},
      };

      const formattedTime = formatTime(showTime);
      if (!group.dates[showDate]) {
        group.dates[showDate] = new Set();
      }
      group.dates[showDate].add(formattedTime);

      grouped.set(key, group);
    });

    return Array.from(grouped.values())
      .map((item, index) => {
        const fallbackCinema = vendorSlug ? getCinemaBySlug(vendorSlug) : getCinemaFallback(index);
        const cinemaSlug = resolveCinemaSlug(item.cinemaRaw) || fallbackCinema?.slug || "";
        const cinemaName =
          getCinemaBySlug(cinemaSlug)?.name || item.cinemaRaw || fallbackCinema?.name || "Cinema";
        const days = buildDaysFromDates(item.dates);
        return { ...item, cinemaSlug, cinemaName, days };
      })
      .filter((item) => Array.isArray(item.days) && item.days.length > 0);
  }, [movies, showtimes, vendorSlug]);

  const visibleItems = useMemo(() => {
    if (!vendorSlug) return scheduleItems;
    return scheduleItems.filter((item) => item.cinemaSlug === vendorSlug);
  }, [scheduleItems, vendorSlug]);

  const openInfo = (item) => {
    if (!item) return;
    const movieId = String(item.movieId || "").trim();
    const movieSlug = String(item.movieSlug || "").trim();

    if (movieId) {
      navigate(`/movie/${movieId}`, { state: { movie: item } });
      return;
    }
    if (movieSlug) {
      navigate(`/movie/${encodeURIComponent(movieSlug)}`, { state: { movie: item } });
      return;
    }
    navigate("/movies");
  };

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
                    {resolvePosterUrl(item) ? (
                      <img src={resolvePosterUrl(item)} alt={item.title} />
                    ) : (
                      <div className="schedule-posterFallback" aria-label={`${item.title} poster unavailable`}>
                        <span>{shortTitle(item.title)}</span>
                      </div>
                    )}
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
                <button
                  className="schedule-infoBtn"
                  type="button"
                  onClick={() => openInfo(item)}
                >
                  Info
                </button>
              </div>

              <div className="schedule-right">
                <div className="schedule-rightTop">
                  <span className="schedule-rightLabel">{item.language.slice(0, 3).toUpperCase()}</span>
                </div>
                <div className="schedule-daysRow">
                  {item.days.map((day) => (
                    <div className="schedule-dayHead" key={`${item.title}-${day.label}-head`}>
                      {day.label}
                      <span>{day.date}</span>
                    </div>
                  ))}
                </div>
                <div className="schedule-timesRow">
                  {item.days.map((day) => (
                    <div className="schedule-dayTimes" key={`${item.title}-${day.label}-times`}>
                      {(day.times || []).map((time) => (
                        <button
                          className="schedule-time"
                          type="button"
                          key={`${day.label}-${time}`}
                          onClick={() =>
                            navigate("/booking", {
                              state: {
                                movie: item,
                                vendor: {
                                  name: item.cinemaName,
                                  slug: item.cinemaSlug,
                                },
                                date: day.iso || day.date,
                                time,
                              },
                            })
                          }
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
              ×
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

function buildMovieIndex(movies) {
  const index = new Map();
  (Array.isArray(movies) ? movies : []).forEach((movie) => {
    if (!movie) return;
    const id = String(movie.id || movie._id || "").trim();
    const title = String(movie.title || movie.name || "").trim().toLowerCase();
    if (id) index.set(id, movie);
    if (title) index.set(title, movie);
  });
  return index;
}

function resolveMovieForShow(show, movieIndex) {
  if (!show) return null;
  const movieId = String(show.movieId || show.movie_id || "").trim();
  if (movieId && movieIndex.has(movieId)) return movieIndex.get(movieId);
  const title = String(show.movie || show.movie_title || show.title || show.name || "")
    .trim()
    .toLowerCase();
  if (title && movieIndex.has(title)) return movieIndex.get(title);
  return null;
}

function buildDaysFromDates(datesMap) {
  const entries = Object.entries(datesMap || {});
  return entries
    .map(([date, times]) => {
      const label = formatDayLabel(date);
      const dateLabel = formatShortDate(date);
      const timesList = Array.from(times || []).filter(Boolean).sort(compareShowTimes);
      const sortKey = new Date(date).getTime();
      return { label, date: dateLabel, iso: date, times: timesList, sortKey };
    })
    .sort((a, b) => (a.sortKey || 0) - (b.sortKey || 0))
    .map(({ sortKey, ...rest }) => rest);
}

function formatDayLabel(dateValue) {
  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) return "Day";
  const today = new Date();
  const isToday = date.toDateString() === today.toDateString();
  if (isToday) return "Today";
  return date.toLocaleDateString("en-GB", { weekday: "short" });
}

function formatShortDate(dateValue) {
  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) return String(dateValue);
  return date.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

function formatTime(value) {
  if (!value) return "";
  if (value.toLowerCase().includes("am") || value.toLowerCase().includes("pm")) return value;
  const [hours, minutes] = value.split(":").map((part) => Number(part));
  if (Number.isNaN(hours) || Number.isNaN(minutes)) return value;
  const period = hours >= 12 ? "PM" : "AM";
  const adjusted = hours % 12 || 12;
  return `${String(adjusted).padStart(2, "0")}:${String(minutes).padStart(2, "0")} ${period}`;
}

function compareShowTimes(left, right) {
  const leftMinutes = toMinutes(left);
  const rightMinutes = toMinutes(right);
  if (leftMinutes === null || rightMinutes === null) return String(left).localeCompare(String(right));
  return leftMinutes - rightMinutes;
}

function toMinutes(value) {
  const text = String(value || "").trim().toUpperCase();
  if (!text) return null;

  const twelveHour = text.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/);
  if (twelveHour) {
    let hour = Number(twelveHour[1]) % 12;
    const minute = Number(twelveHour[2]);
    if (Number.isNaN(hour) || Number.isNaN(minute)) return null;
    if (twelveHour[3] === "PM") hour += 12;
    return hour * 60 + minute;
  }

  const twentyFourHour = text.match(/^(\d{1,2}):(\d{2})$/);
  if (twentyFourHour) {
    const hour = Number(twentyFourHour[1]);
    const minute = Number(twentyFourHour[2]);
    if (Number.isNaN(hour) || Number.isNaN(minute)) return null;
    return hour * 60 + minute;
  }

  return null;
}

function resolvePosterUrl(item) {
  return String(item?.poster || "").trim();
}

function shortTitle(value) {
  const text = String(value || "").trim();
  if (!text) return "MOVIE";
  return text
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}
