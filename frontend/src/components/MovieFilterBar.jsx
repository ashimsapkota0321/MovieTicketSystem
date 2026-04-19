import React, { useState, useMemo, useEffect } from "react";

export default function MovieFilterBar({ movies, onFilter }) {
  const [period, setPeriod] = useState("thisWeek");
  const [language, setLanguage] = useState("All");

  // Get unique languages from movies
  const languages = useMemo(() => {
    const set = new Set(movies.map(m => m.language).filter(Boolean));
    return ["All", ...Array.from(set)];
  }, [movies]);

  // Filter movies by period and language
  const filteredMovies = useMemo(() => {
    const now = new Date();
    const startOfWeek = new Date(now);
    startOfWeek.setDate(now.getDate() - now.getDay());
    const endOfWeek = new Date(startOfWeek);
    endOfWeek.setDate(startOfWeek.getDate() + 6);

    const startOfNextWeek = new Date(endOfWeek);
    startOfNextWeek.setDate(endOfWeek.getDate() + 1);
    const endOfNextWeek = new Date(startOfNextWeek);
    endOfNextWeek.setDate(startOfNextWeek.getDate() + 6);

    return movies.filter(movie => {
      // Filter by language
      if (language !== "All" && movie.language !== language) return false;
      // Filter by period
      const showDate = new Date(movie.showDate);
      if (period === "thisWeek") {
        return showDate >= startOfWeek && showDate <= endOfWeek;
      } else if (period === "nextWeek") {
        return showDate >= startOfNextWeek && showDate <= endOfNextWeek;
      }
      return true;
    });
  }, [movies, period, language]);

  useEffect(() => {
    onFilter(filteredMovies);
  }, [filteredMovies, onFilter]);

  return (
    <div style={{
      background: "#44454a",
      borderRadius: "16px",
      padding: "24px",
      display: "flex",
      alignItems: "center",
      gap: "32px",
      margin: "24px 0"
    }}>
      <span style={{ fontWeight: 500, color: "#fff" }}>Period</span>
      <button
        className={period === "thisWeek" ? "active" : ""}
        onClick={() => setPeriod("thisWeek")}
      >
        This Week
      </button>
      <button
        className={period === "nextWeek" ? "active" : ""}
        onClick={() => setPeriod("nextWeek")}
      >
        Next Week
      </button>
      <span style={{ fontWeight: 500, color: "#fff", marginLeft: "32px" }}>Language</span>
      <select
        value={language}
        onChange={e => setLanguage(e.target.value)}
        style={{
          background: "#23232a",
          color: "#fff",
          border: "none",
          borderRadius: "12px",
          padding: "8px 16px",
          fontWeight: 600
        }}
      >
        {languages.map(lang => (
          <option key={lang} value={lang}>{lang}</option>
        ))}
      </select>
      <style>{`
        button {
          background: none;
          border: none;
          color: #fff;
          font-weight: 600;
          font-size: 1rem;
          padding: 8px 20px;
          border-radius: 24px;
          margin-right: 8px;
          cursor: pointer;
        }
        button.active {
          background: #0ec3e0;
          color: #fff;
          border: 2px solid #0ec3e0;
        }
        select:focus, button:focus {
          outline: 2px solid #0ec3e0;
        }
      `}</style>
    </div>
  );
}
