import { useMemo, useState } from "react";
import { CalendarRange, List } from "lucide-react";
import AdminPageHeader from "./components/AdminPageHeader";
import { useAppContext } from "../context/Appcontext";

const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function AdminSchedule() {
  const [view, setView] = useState("calendar");
  const ctx = safeUseAppContext();
  const shows = ctx?.showtimes ?? [];
  const vendors = ctx?.vendors ?? [];
  const movies = ctx?.movies ?? [];

  const calendarDays = useMemo(() => {
    const daysInMonth = 28;
    return Array.from({ length: daysInMonth }, (_, index) => {
      const day = index + 1;
      const dayString = String(day).padStart(2, "0");
      const date = `2026-02-${dayString}`;
      return {
        day,
        date,
        isToday: date === "2026-02-15",
        hasShow: shows.some((show) => show.date === date),
      };
    });
  }, [shows]);

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
          <div className="d-flex gap-2 flex-wrap">
            <select className="form-select">
              <option>Vendor</option>
              {vendors.map((vendor) => (
                <option key={vendor.id}>{vendor.name}</option>
              ))}
            </select>
            <select className="form-select">
              <option>Movie</option>
              {movies.map((movie) => (
                <option key={movie.id}>{movie.title}</option>
              ))}
            </select>
            <input type="date" className="form-control" defaultValue="2026-02-15" />
          </div>
        </div>

        {view === "calendar" ? (
          <div className="admin-calendar">
            {dayNames.map((day) => (
              <div key={day} className="day-name">
                {day}
              </div>
            ))}
            {calendarDays.map((day) => (
              <div key={day.date} className={`day ${day.isToday ? "today" : ""}`}>
                <div className="d-flex justify-content-between align-items-center">
                  <span className="fw-semibold">{day.day}</span>
                  {day.hasShow ? <span className="dot" /> : null}
                </div>
                <small className="text-muted">{day.hasShow ? "Shows scheduled" : "No shows"}</small>
              </div>
            ))}
          </div>
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
                {shows.map((show) => (
                  <tr key={show.id}>
                    <td>{show.date}</td>
                    <td>{show.movie}</td>
                    <td>{show.vendor}</td>
                    <td>{show.hall}</td>
                    <td>{show.slot}</td>
                    <td>
                      {show.start} - {show.end}
                    </td>
                    <td>
                      <span
                        className={`badge-soft ${show.status === "Open" ? "success" : show.status === "Sold Out" ? "warning" : "info"}`}
                      >
                        {show.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <nav className="d-flex justify-content-between align-items-center mt-3">
              <span className="text-muted small">Page 1 of 2</span>
              <ul className="pagination mb-0">
                <li className="page-item disabled"><span className="page-link">Prev</span></li>
                <li className="page-item active"><span className="page-link">1</span></li>
                <li className="page-item"><span className="page-link">2</span></li>
                <li className="page-item"><span className="page-link">Next</span></li>
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
