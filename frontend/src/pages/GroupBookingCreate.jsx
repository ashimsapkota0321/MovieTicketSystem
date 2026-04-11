import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  createGroupBookingSession,
  fetchGroupBookingSessions,
} from "../lib/catalogApi";
import "../css/groupBooking.css";

function normalizeSeats(value) {
  return Array.from(
    new Set(
      String(value || "")
        .toUpperCase()
        .split(/[,\s]+/)
        .map((item) => item.trim())
        .filter(Boolean)
    )
  );
}

function toMoney(value) {
  return `NPR ${Number(value || 0).toFixed(2)}`;
}

export default function GroupBookingCreate() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location?.state || {};

  const bookingContext = useMemo(() => state.bookingContext || {}, [state.bookingContext]);
  const selectedSeatsFromState = useMemo(() => {
    if (Array.isArray(state.selectedSeats)) return state.selectedSeats;
    if (Array.isArray(bookingContext.selectedSeats)) return bookingContext.selectedSeats;
    return [];
  }, [state.selectedSeats, bookingContext.selectedSeats]);

  const [form, setForm] = useState({
    show_id: String(bookingContext.showId || bookingContext.show_id || state.showId || ""),
    movie_id: String(bookingContext.movieId || bookingContext.movie_id || ""),
    cinema_id: String(bookingContext.cinemaId || bookingContext.cinema_id || ""),
    date: String(bookingContext.date || bookingContext.showDate || ""),
    time: String(bookingContext.time || bookingContext.showTime || ""),
    hall: String(bookingContext.hall || ""),
    selected_seats: selectedSeatsFromState.join(", "),
    split_mode: "EQUAL",
    expiry_minutes: "12",
  });

  const [submitting, setSubmitting] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [error, setError] = useState("");
  const [createdSession, setCreatedSession] = useState(null);
  const [sessions, setSessions] = useState([]);

  const canSubmit = useMemo(() => {
    const seatList = normalizeSeats(form.selected_seats);
    const hasShowId = Number(form.show_id) > 0;
    const hasContext =
      Number(form.movie_id) > 0 &&
      Number(form.cinema_id) > 0 &&
      Boolean(form.date) &&
      Boolean(form.time);
    return seatList.length > 0 && (hasShowId || hasContext);
  }, [form]);

  const loadSessions = async () => {
    setLoadingSessions(true);
    try {
      const data = await fetchGroupBookingSessions();
      setSessions(Array.isArray(data) ? data : []);
    } catch {
      setSessions([]);
    } finally {
      setLoadingSessions(false);
    }
  };

  useEffect(() => {
    loadSessions();
  }, []);

  const updateField = (key, value) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleCreate = async (event) => {
    event.preventDefault();
    if (!canSubmit || submitting) return;

    setSubmitting(true);
    setError("");
    try {
      const seatList = normalizeSeats(form.selected_seats);
      const payload = {
        split_mode: form.split_mode,
        selected_seats: seatList,
        expiry_minutes: Number(form.expiry_minutes || 12),
      };

      if (Number(form.show_id) > 0) {
        payload.show_id = Number(form.show_id);
      } else {
        payload.movie_id = Number(form.movie_id || 0);
        payload.cinema_id = Number(form.cinema_id || 0);
        payload.date = form.date;
        payload.time = form.time;
      }
      if (form.hall) payload.hall = form.hall;

      const response = await createGroupBookingSession(payload);
      const session = response?.session || null;
      if (!session) {
        throw new Error("Failed to create group booking session.");
      }

      setCreatedSession(session);
      await loadSessions();
    } catch (err) {
      setError(err?.message || "Unable to create group booking session.");
    } finally {
      setSubmitting(false);
    }
  };

  const copyInviteLink = async () => {
    if (!createdSession?.invite_link) return;
    try {
      await navigator.clipboard.writeText(createdSession.invite_link);
    } catch {
      // Ignore clipboard failures in unsupported environments.
    }
  };

  return (
    <div className="gb-page">
      <div className="gb-shell">
        <header className="gb-header">
          <h1>Group Booking</h1>
          <p>Create a session, share the invite code, and split payment.</p>
        </header>

        <section className="gb-card">
          <h2>Create Session</h2>
          <form className="gb-form" onSubmit={handleCreate}>
            <label>
              Show ID (optional)
              <input
                type="number"
                min="1"
                value={form.show_id}
                onChange={(event) => updateField("show_id", event.target.value)}
              />
            </label>

            <div className="gb-grid-2">
              <label>
                Movie ID
                <input
                  type="number"
                  min="1"
                  value={form.movie_id}
                  onChange={(event) => updateField("movie_id", event.target.value)}
                />
              </label>
              <label>
                Cinema ID
                <input
                  type="number"
                  min="1"
                  value={form.cinema_id}
                  onChange={(event) => updateField("cinema_id", event.target.value)}
                />
              </label>
            </div>

            <div className="gb-grid-3">
              <label>
                Date
                <input
                  type="date"
                  value={form.date}
                  onChange={(event) => updateField("date", event.target.value)}
                />
              </label>
              <label>
                Time
                <input
                  type="time"
                  value={form.time}
                  onChange={(event) => updateField("time", event.target.value)}
                />
              </label>
              <label>
                Hall
                <input
                  type="text"
                  value={form.hall}
                  onChange={(event) => updateField("hall", event.target.value)}
                  placeholder="Hall A"
                />
              </label>
            </div>

            <label>
              Seats (comma separated)
              <input
                type="text"
                value={form.selected_seats}
                onChange={(event) => updateField("selected_seats", event.target.value)}
                placeholder="A1, A2, A3"
              />
            </label>

            <div className="gb-grid-2">
              <label>
                Split Mode
                <select
                  value={form.split_mode}
                  onChange={(event) => updateField("split_mode", event.target.value)}
                >
                  <option value="EQUAL">Equal Split</option>
                  <option value="MANUAL">Manual Split (host decides)</option>
                  <option value="SEAT_BASED">Seat-Based Split</option>
                </select>
              </label>

              <label>
                Expiry (minutes)
                <input
                  type="number"
                  min="10"
                  max="20"
                  value={form.expiry_minutes}
                  onChange={(event) => updateField("expiry_minutes", event.target.value)}
                />
              </label>
            </div>

            {error ? <p className="gb-error">{error}</p> : null}

            <button type="submit" className="gb-btn gb-btn-primary" disabled={!canSubmit || submitting}>
              {submitting ? "Creating..." : "Create Session"}
            </button>
          </form>
        </section>

        {createdSession ? (
          <section className="gb-card gb-highlight">
            <h2>Session Created</h2>
            <p>
              Invite code: <strong>{createdSession.invite_code}</strong>
            </p>
            <p className="gb-mono">{createdSession.invite_link}</p>
            <div className="gb-actions">
              <button type="button" className="gb-btn" onClick={copyInviteLink}>
                Copy Invite Link
              </button>
              <button
                type="button"
                className="gb-btn gb-btn-primary"
                onClick={() => navigate(`/group-booking/session/${createdSession.invite_code}`)}
              >
                Open Session
              </button>
            </div>
          </section>
        ) : null}

        <section className="gb-card">
          <div className="gb-card-head">
            <h2>Recent Sessions</h2>
            <button type="button" className="gb-btn" onClick={loadSessions} disabled={loadingSessions}>
              {loadingSessions ? "Refreshing..." : "Refresh"}
            </button>
          </div>

          {!sessions.length ? (
            <p className="gb-muted">No group sessions yet.</p>
          ) : (
            <div className="gb-session-list">
              {sessions.map((session) => (
                <article key={session.id} className="gb-session-item">
                  <div>
                    <h3>
                      {session?.show?.movie_title || "Movie"} | {session?.show?.show_date || "-"} {session?.show?.show_time || ""}
                    </h3>
                    <p className="gb-muted">
                      Status: {session.status} | Split: {session.split_mode} | Total: {toMoney(session.total_amount)}
                    </p>
                    <p className="gb-muted">
                      Seats: {(session.selected_seats || []).join(", ") || "-"}
                    </p>
                  </div>
                  <div className="gb-actions">
                    <button
                      type="button"
                      className="gb-btn"
                      onClick={() => navigate(`/group-booking/session/${session.invite_code}`)}
                    >
                      Open
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
