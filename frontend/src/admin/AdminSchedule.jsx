import { useMemo, useState } from "react";
import { CalendarRange, ChevronLeft, ChevronRight, List } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import { useAppContext } from "../context/Appcontext";

const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const monthFormatter = new Intl.DateTimeFormat("en-US", {
  month: "long",
  year: "numeric",
});

export default function AdminSchedule() {
  const [view, setView] = useState("calendar");
  const [selectedVendor, setSelectedVendor] = useState("");
  const [selectedMovie, setSelectedMovie] = useState("");
  const [selectedDate, setSelectedDate] = useState(() => formatDateKey(new Date()));
  const [displayMonth, setDisplayMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });

  const ctx = safeUseAppContext();
  const shows = ctx?.showtimes ?? [];
  const vendors = ctx?.vendors ?? [];
  const movies = ctx?.movies ?? [];

  const normalizedShows = useMemo(
    () =>
      shows
        .map((show) => {
          const dateValue = normalizeIsoDate(show?.date || show?.show_date || show?.showDate);
          if (!dateValue) return null;

          return {
            id: show?.id || `${dateValue}-${show?.movie || show?.movie_title || "show"}`,
            dateValue,
            movieLabel: firstNonEmpty(show?.movie, show?.movie_title, show?.title, show?.name, "Movie"),
            vendorLabel: firstNonEmpty(
              show?.vendor,
              show?.vendor_name,
              show?.vendorName,
              show?.cinema,
              "Vendor"
            ),
            hallLabel: firstNonEmpty(show?.hall, show?.screen, show?.screen_name, "-"),
            slotLabel: firstNonEmpty(show?.slot, guessSlot(show?.start || show?.start_time || show?.startTime)),
            startLabel: firstNonEmpty(show?.start, show?.start_time, show?.startTime, "-"),
            endLabel: firstNonEmpty(show?.end, show?.end_time, show?.endTime, "-"),
            statusLabel: firstNonEmpty(show?.status, "Open"),
          };
        })
        .filter(Boolean),
    [shows]
  );

  const vendorOptions = useMemo(() => {
    const vendorSet = new Set(
      vendors
        .map((vendor) => String(vendor?.name || "").trim())
        .filter(Boolean)
    );
    normalizedShows.forEach((show) => vendorSet.add(show.vendorLabel));
    return Array.from(vendorSet).sort((a, b) => a.localeCompare(b));
  }, [vendors, normalizedShows]);

  const movieOptions = useMemo(() => {
    const movieSet = new Set(
      movies
        .map((movie) => String(movie?.title || movie?.name || "").trim())
        .filter(Boolean)
    );
    normalizedShows.forEach((show) => movieSet.add(show.movieLabel));
    return Array.from(movieSet).sort((a, b) => a.localeCompare(b));
  }, [movies, normalizedShows]);

  const calendarShows = useMemo(
    () =>
      normalizedShows.filter(
        (show) =>
          (!selectedVendor || show.vendorLabel === selectedVendor) &&
          (!selectedMovie || show.movieLabel === selectedMovie)
      ),
    [normalizedShows, selectedVendor, selectedMovie]
  );

  const listShows = useMemo(
    () =>
      calendarShows
        .filter((show) => !selectedDate || show.dateValue === selectedDate)
        .sort((left, right) => {
          if (left.dateValue !== right.dateValue) {
            return left.dateValue.localeCompare(right.dateValue);
          }
          return String(left.startLabel).localeCompare(String(right.startLabel));
        }),
    [calendarShows, selectedDate]
  );

  const showsByDate = useMemo(() => {
    const grouped = new Map();
    calendarShows.forEach((show) => {
      const current = grouped.get(show.dateValue) || [];
      current.push(show);
      grouped.set(show.dateValue, current);
    });
    return grouped;
  }, [calendarShows]);

  const calendarCells = useMemo(() => {
    const year = displayMonth.getFullYear();
    const month = displayMonth.getMonth();
    const firstWeekday = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const leading = Array.from({ length: firstWeekday }, (_, index) => ({
      key: `lead-${year}-${month}-${index}`,
      empty: true,
    }));

    const nowKey = formatDateKey(new Date());
    const activeDays = Array.from({ length: daysInMonth }, (_, index) => {
      const day = index + 1;
      const dateKey = formatDateKey(new Date(year, month, day));
      const dailyShows = showsByDate.get(dateKey) || [];

      return {
        key: dateKey,
        empty: false,
        day,
        dateKey,
        showCount: dailyShows.length,
        isToday: dateKey === nowKey,
        isSelected: selectedDate === dateKey,
      };
    });

    const trailingCount = (7 - ((leading.length + activeDays.length) % 7)) % 7;
    const trailing = Array.from({ length: trailingCount }, (_, index) => ({
      key: `trail-${year}-${month}-${index}`,
      empty: true,
    }));

    return [...leading, ...activeDays, ...trailing];
  }, [displayMonth, selectedDate, showsByDate]);

  const monthTitle = monthFormatter.format(displayMonth);

  const handleDateChange = (value) => {
    setSelectedDate(value);
    if (!value) return;
    const date = parseIsoDate(value);
    if (!date) return;
    setDisplayMonth(new Date(date.getFullYear(), date.getMonth(), 1));
  };

  const goToPreviousMonth = () => {
    setDisplayMonth(
      (current) => new Date(current.getFullYear(), current.getMonth() - 1, 1)
    );
  };

  const goToNextMonth = () => {
    setDisplayMonth(
      (current) => new Date(current.getFullYear(), current.getMonth() + 1, 1)
    );
  };

  return (
    <>
      <AdminPageHeader
        title="Manage Schedule"
        subtitle="Calendar and list view of the show timetable."
      >
        <div className="btn-group" role="group">
          <button
            type="button"
            className={`btn ${view === "calendar" ? "btn-primary" : "btn-outline-light"}`}
            onClick={() => setView("calendar")}
          >
            <CalendarRange size={16} className="me-2" />
            Calendar
          </button>
          <button
            type="button"
            className={`btn ${view === "list" ? "btn-primary" : "btn-outline-light"}`}
            onClick={() => setView("list")}
          >
            <List size={16} className="me-2" />
            List
          </button>
        </div>
      </AdminPageHeader>

      <section className="admin-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div className="d-flex gap-2 flex-wrap admin-filter-row">
            <select
              className="form-select"
              value={selectedVendor}
              onChange={(event) => setSelectedVendor(event.target.value)}
            >
              <option value="">All vendors</option>
              {vendorOptions.map((vendorName) => (
                <option key={vendorName} value={vendorName}>
                  {vendorName}
                </option>
              ))}
            </select>
            <select
              className="form-select"
              value={selectedMovie}
              onChange={(event) => setSelectedMovie(event.target.value)}
            >
              <option value="">All movies</option>
              {movieOptions.map((movieTitle) => (
                <option key={movieTitle} value={movieTitle}>
                  {movieTitle}
                </option>
              ))}
            </select>
            <input
              type="date"
              className="form-control"
              value={selectedDate}
              onChange={(event) => handleDateChange(event.target.value)}
            />
          </div>
          <div className="text-muted small">{calendarShows.length} filtered shows</div>
        </div>

        {view === "calendar" ? (
          <>
            <div className="d-flex justify-content-between align-items-center mb-3">
              <div className="d-flex gap-2 align-items-center">
                <button type="button" className="btn btn-outline-light btn-sm" onClick={goToPreviousMonth}>
                  <ChevronLeft size={16} />
                </button>
                <button type="button" className="btn btn-outline-light btn-sm" onClick={goToNextMonth}>
                  <ChevronRight size={16} />
                </button>
              </div>
              <h6 className="mb-0 fw-semibold">{monthTitle}</h6>
              <button
                type="button"
                className="btn btn-outline-light btn-sm"
                onClick={() => {
                  const today = new Date();
                  const todayKey = formatDateKey(today);
                  setDisplayMonth(new Date(today.getFullYear(), today.getMonth(), 1));
                  setSelectedDate(todayKey);
                }}
              >
                Today
              </button>
            </div>

            <div className="admin-calendar">
              {dayNames.map((day) => (
                <div key={day} className="day-name">
                  {day}
                </div>
              ))}
              {calendarCells.map((day) => {
                if (day.empty) {
                  return <div key={day.key} className="day day-empty" aria-hidden="true" />;
                }

                return (
                  <button
                    key={day.key}
                    type="button"
                    className={`day ${day.isToday ? "today" : ""} ${day.isSelected ? "selected" : ""}`}
                    onClick={() => setSelectedDate(day.dateKey)}
                  >
                    <div className="d-flex justify-content-between align-items-center">
                      <span className="fw-semibold">{day.day}</span>
                      {day.showCount > 0 ? <span className="dot" /> : null}
                    </div>
                    <small className="text-muted">
                      {day.showCount > 0 ? `${day.showCount} show${day.showCount > 1 ? "s" : ""}` : "No shows"}
                    </small>
                  </button>
                );
              })}
            </div>
          </>
        ) : (
          <div className="table-responsive">
            <table className="table admin-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Movie</th>
                  <th>Vendor</th>
                  <th>Hall</th>
                  <th>Slot</th>
                  <th>Time</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {listShows.map((show) => (
                  <tr key={show.id}>
                    <td>{formatReadableDate(show.dateValue)}</td>
                    <td>{show.movieLabel}</td>
                    <td>{show.vendorLabel}</td>
                    <td>{show.hallLabel}</td>
                    <td>{show.slotLabel}</td>
                    <td>
                      {show.startLabel} - {show.endLabel}
                    </td>
                    <td>
                      <span
                        className={`badge-soft ${
                          show.statusLabel === "Open"
                            ? "success"
                            : show.statusLabel === "Sold Out"
                            ? "warning"
                            : "info"
                        }`}
                      >
                        {show.statusLabel}
                      </span>
                    </td>
                  </tr>
                ))}
                {listShows.length === 0 ? (
                  <tr>
                    <td colSpan="7">No schedules match the selected filters.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
            <nav className="d-flex justify-content-between align-items-center mt-3">
              <span className="text-muted small">Showing {listShows.length} schedules</span>
              <ul className="pagination mb-0">
                <li className="page-item disabled"><span className="page-link">Prev</span></li>
                <li className="page-item active"><span className="page-link">1</span></li>
                <li className="page-item disabled"><span className="page-link">Next</span></li>
              </ul>
            </nav>
          </div>
        )}
      </section>
    </>
  );
}

function safeUseAppContext() {
  try {
    return useAppContext?.();
  } catch {
    return null;
  }
}

function firstNonEmpty(...values) {
  for (const value of values) {
    const text = String(value ?? "").trim();
    if (text) return text;
  }
  return "";
}

function formatDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseIsoDate(value) {
  if (!value) return null;
  const trimmed = String(value).trim();
  const parts = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (parts) {
    return new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]));
  }

  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) return null;
  return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
}

function normalizeIsoDate(value) {
  const parsed = parseIsoDate(value);
  return parsed ? formatDateKey(parsed) : "";
}

function guessSlot(startTime) {
  const value = String(startTime ?? "").trim();
  const hour = Number(value.slice(0, 2));
  if (Number.isNaN(hour)) return "-";
  if (hour < 12) return "Morning";
  if (hour < 17) return "Matinee";
  if (hour < 21) return "Evening";
  return "Night";
}

function formatReadableDate(value) {
  const parsed = parseIsoDate(value);
  if (!parsed) return value || "-";
  return new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(parsed);
}
