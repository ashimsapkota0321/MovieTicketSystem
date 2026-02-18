import React, { useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ChevronLeft } from "lucide-react";
import "../css/movieSchedule.css";
import { useAppContext } from "../context/Appcontext";
import { cinemaVendors } from "../lib/cinemas";

import gharjwai from "../images/gharjwai.jpg";
import balidan from "../images/balidan.jpg";
import degreemaila from "../images/degreemaila.jpg";
import avengers from "../images/avengers.jpg";

export default function MovieSchedule() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const ctx = safeUseAppContext();
  const shows = ctx?.movies ?? ctx?.shows ?? fallbackShows;
  const showtimes = ctx?.showtimes ?? [];
  const stateMovie = location?.state?.movie || null;

  const movie = useMemo(
    () => stateMovie || findMovie(shows, id) || fallbackShows[0],
    [stateMovie, shows, id]
  );
  const title = movie?.title || movie?.name || "Movie Title";
  const duration = toText(movie?.duration) || "2h 10m";
  const genre = toText(movie?.genre || movie?.category || movie?.type) || "Action, Comedy";
  const year = toText(movie?.year || movie?.releaseDate) || "2025";
  const censor = toText(movie?.censor || movie?.rating || movie?.certificate) || "UA 13+";
  const metaLine = [duration, genre, year, censor].filter(Boolean).join(" | ");

  const [activeDate, setActiveDate] = useState(0);
  const [priceRange, setPriceRange] = useState("all");
  const [preferredTime, setPreferredTime] = useState("all");

  const movieShowDates = useMemo(() => collectShowDates(showtimes, movie), [showtimes, movie]);
  const dateOptions = useMemo(() => buildDateOptions(7, movieShowDates), [movieShowDates]);
  const activeDateValue = dateOptions[activeDate]?.iso || "";
  const showtimeRows = useMemo(() => {
    const rows = buildShowtimeRowsFromShows(showtimes, movie, activeDateValue, cinemaVendors);
    return rows.length ? rows : buildShowtimeRows(cinemaVendors);
  }, [showtimes, movie, activeDateValue]);

  return (
    <div className="wf2-page movieSchedule-page">
      <div className="wf2-container movieSchedule-wrap">
        <div className="movieSchedule-head">
          <button
            className="movieSchedule-backBtn"
            type="button"
            onClick={() => navigate(-1)}
            aria-label="Go back"
          >
            <ChevronLeft size={18} />
          </button>
          <div>
            <h2 className="movieSchedule-title">{title}</h2>
            <p className="movieSchedule-meta">{metaLine}</p>
          </div>
        </div>

        <div className="movieSchedule-toolbar">
          <div className="movieSchedule-dates">
            {dateOptions.map((option, index) => (
              <button
                key={option.key}
                type="button"
                className={`movieSchedule-date ${
                  index === activeDate ? "movieSchedule-dateActive" : ""
                }`}
                onClick={() => setActiveDate(index)}
              >
                <span>{option.label}</span>
                <strong>{option.date}</strong>
              </button>
            ))}
          </div>

          <div className="movieSchedule-filters">
            <select
              className="movieSchedule-select"
              value={priceRange}
              onChange={(event) => setPriceRange(event.target.value)}
            >
              <option value="all">Price Range</option>
              <option value="150-200">NPR 150 - 200</option>
              <option value="200-300">NPR 200 - 300</option>
              <option value="300-400">NPR 300 - 400</option>
            </select>
            <select
              className="movieSchedule-select"
              value={preferredTime}
              onChange={(event) => setPreferredTime(event.target.value)}
            >
              <option value="all">Preferred Time</option>
              <option value="morning">Morning</option>
              <option value="afternoon">Afternoon</option>
              <option value="evening">Evening</option>
            </select>
          </div>
        </div>

        <div className="movieSchedule-list">
          {showtimeRows.map((row) => (
            <div className="movieSchedule-card" key={row.vendor.slug}>
              <div className="movieSchedule-cinema">
                <div className="movieSchedule-cinemaName">{row.vendor.name}</div>
                <div className="movieSchedule-cinemaLocation">{row.location}</div>
              </div>
              <div className="movieSchedule-times">
                {row.times.map((time) => (
                  <button
                    key={`${row.vendor.slug}-${time}`}
                    className="movieSchedule-time"
                    type="button"
                    onClick={() => navigate("/booking")}
                  >
                    {time}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
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
  const direct = shows.find((show) => `${show._id}` === id || `${show.id}` === id);
  if (direct) return direct;
  return shows.find((show) => {
    const title = (show.title || show.name || "").trim();
    if (!title) return false;
    return title === decoded || encodeURIComponent(title) === id;
  });
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

function buildDateOptions(count, extraDates = []) {
  const today = new Date();
  const baseDates = Array.from({ length: count }, (_, index) => {
    const date = new Date(today);
    date.setDate(today.getDate() + index);
    return date.toISOString().slice(0, 10);
  });

  const uniqueDates = new Set([...baseDates, ...extraDates.filter(Boolean)]);

  return Array.from(uniqueDates)
    .map((iso) => {
      const date = new Date(iso);
      const isToday = date.toDateString() === today.toDateString();
      const label = isToday ? "Today" : date.toLocaleDateString("en-GB", { weekday: "short" });
      const dateLabel = date.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
      });
      return {
        key: `${label}-${dateLabel}-${iso}`,
        label,
        date: dateLabel,
        iso,
        sortKey: date.getTime(),
      };
    })
    .sort((a, b) => (a.sortKey || 0) - (b.sortKey || 0))
    .map(({ sortKey, ...rest }) => rest);
}

function buildShowtimeRows(vendors) {
  const timeSets = [
    ["08:30 AM", "10:00 AM", "02:00 PM"],
    ["10:00 AM", "01:00 PM", "05:30 PM"],
    ["09:30 AM", "12:00 PM", "05:00 PM"],
    ["10:00 AM", "02:00 PM", "08:00 PM"],
  ];
  return vendors.map((vendor, index) => ({
    vendor,
    location: vendor.locations[0] || "Kathmandu",
    times: timeSets[index % timeSets.length],
  }));
}

function collectShowDates(shows, movie) {
  if (!Array.isArray(shows) || !movie) return [];
  const dates = new Set();
  shows.forEach((show) => {
    if (!matchesMovie(show, movie)) return;
    const value = String(show.date || show.show_date || show.showDate || "").trim();
    if (value) dates.add(value);
  });
  return Array.from(dates);
}

function buildShowtimeRowsFromShows(shows, movie, activeDate, vendors) {
  if (!Array.isArray(shows) || !movie) return [];
  const grouped = new Map();
  shows.forEach((show) => {
    if (!matchesMovie(show, movie)) return;
    const showDate = String(show.date || show.show_date || show.showDate || "").trim();
    if (activeDate && showDate && showDate !== activeDate) return;
    const vendorName = String(show.vendor || show.vendor_name || show.vendorName || show.cinema || "").trim();
    if (!vendorName) return;
    const key = vendorName.toLowerCase();
    const startTime = String(show.start || show.start_time || show.startTime || "").trim();
    if (!startTime) return;
    const formattedTime = formatTime(startTime);
    const existing = grouped.get(key);
    if (existing) {
      if (!existing.times.includes(formattedTime)) {
        existing.times.push(formattedTime);
      }
      return;
    }
    const vendorInfo =
      vendors.find((vendor) => vendor.name.toLowerCase() === vendorName.toLowerCase()) || null;
    grouped.set(key, {
      vendor: vendorInfo || { name: vendorName, slug: key },
      location:
        vendorInfo?.locations?.[0] ||
        show.city ||
        show.location ||
        show.theatre ||
        "Kathmandu",
      times: [formattedTime],
    });
  });
  return Array.from(grouped.values()).map((row) => ({
    ...row,
    times: row.times.sort((a, b) => (a > b ? 1 : -1)),
  }));
}

function matchesMovie(show, movie) {
  if (!show || !movie) return false;
  const movieId = String(movie.id || movie._id || "").trim();
  const showMovieId = String(show.movieId || show.movie_id || "").trim();
  if (movieId && showMovieId && movieId === showMovieId) return true;
  const showTitle = String(show.movie || show.movie_title || show.title || show.name || "")
    .trim()
    .toLowerCase();
  const movieTitle = String(movie.title || movie.name || "")
    .trim()
    .toLowerCase();
  if (!showTitle || !movieTitle) return false;
  return showTitle === movieTitle;
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

const fallbackShows = [
  { _id: "1", title: "Gharjwai", poster: gharjwai },
  { _id: "2", title: "Balidan", poster: balidan },
  { _id: "3", title: "Degree Maila", poster: degreemaila },
  { _id: "4", title: "Avengers", poster: avengers },
];
