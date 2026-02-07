import React, { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
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
  const ctx = safeUseAppContext();
  const shows = ctx?.shows ?? fallbackShows;

  const movie = useMemo(() => findMovie(shows, id) ?? fallbackShows[0], [shows, id]);
  const title = movie?.title || movie?.name || "Movie Title";
  const duration = toText(movie?.duration) || "2h 10m";
  const genre = toText(movie?.genre || movie?.category || movie?.type) || "Action, Comedy";
  const year = toText(movie?.year || movie?.releaseDate) || "2025";
  const censor = toText(movie?.censor || movie?.rating || movie?.certificate) || "UA 13+";
  const metaLine = [duration, genre, year, censor].filter(Boolean).join(" | ");

  const [activeDate, setActiveDate] = useState(0);
  const [priceRange, setPriceRange] = useState("all");
  const [preferredTime, setPreferredTime] = useState("all");

  const dateOptions = useMemo(() => buildDateOptions(7), []);
  const showtimeRows = useMemo(() => buildShowtimeRows(cinemaVendors), []);

  return (
    <div className="wf2-page movieSchedule-page">
      <div className="wf2-container movieSchedule-wrap">
        <div className="movieSchedule-head">
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

function buildDateOptions(count) {
  const today = new Date();
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(today);
    date.setDate(today.getDate() + index);
    const label =
      index === 0
        ? "Today"
        : date.toLocaleDateString("en-GB", { weekday: "short" });
    const dateLabel = date.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
    });
    return {
      key: `${label}-${dateLabel}`,
      label,
      date: dateLabel,
    };
  });
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

const fallbackShows = [
  { _id: "1", title: "Gharjwai", poster: gharjwai },
  { _id: "2", title: "Balidan", poster: balidan },
  { _id: "3", title: "Degree Maila", poster: degreemaila },
  { _id: "4", title: "Avengers", poster: avengers },
];
