import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  applyGroupManualSplit,
  assignGroupBookingSeats,
  cancelGroupBookingSession,
  completeGroupBookingPayment,
  dropOutGroupBookingSession,
  fetchGroupBookingSessionByInvite,
  initiateGroupBookingPayment,
  joinGroupBookingSession,
} from "../lib/catalogApi";
import "../css/groupBooking.css";

function toMoney(value) {
  return `NPR ${Number(value || 0).toFixed(2)}`;
}

function normalizeSeatList(value) {
  return Array.from(
    new Set(
      (Array.isArray(value) ? value : [])
        .map((item) => String(item || "").trim().toUpperCase())
        .filter(Boolean)
    )
  ).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

function buildTransactionId() {
  return `GRP-${Date.now()}-${Math.random().toString(36).slice(2, 8).toUpperCase()}`;
}

export default function GroupBookingSession() {
  const { inviteCode } = useParams();
  const navigate = useNavigate();

  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [seatDraft, setSeatDraft] = useState([]);
  const [manualDraft, setManualDraft] = useState({});

  const loadSession = useCallback(
    async ({ silent = false } = {}) => {
      if (!inviteCode) return;
      if (!silent) setLoading(true);
      try {
        const payload = await fetchGroupBookingSessionByInvite(inviteCode);
        setSession(payload || null);
        setError("");
      } catch (err) {
        setError(err?.message || "Unable to load group booking session.");
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [inviteCode]
  );

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  useEffect(() => {
    if (!session) return;
    const viewerSeats = normalizeSeatList(session?.viewer?.selected_seats || []);
    setSeatDraft(viewerSeats);

    const nextManual = {};
    (session?.participants || []).forEach((participant) => {
      if (!participant.left_at) {
        nextManual[participant.user_id] = String(Number(participant.amount_to_pay || 0).toFixed(2));
      }
    });
    setManualDraft(nextManual);
  }, [session]);

  useEffect(() => {
    if (!session) return;
    if (!["ACTIVE", "PARTIALLY_PAID"].includes(session.status)) return;

    const timer = setInterval(() => {
      loadSession({ silent: true }).catch(() => {});
    }, 8000);
    return () => clearInterval(timer);
  }, [session, loadSession]);

  const participants = session?.participants || [];
  const activeParticipants = useMemo(
    () => participants.filter((item) => !item.left_at),
    [participants]
  );

  const viewer = session?.viewer || {};
  const isParticipant = Boolean(viewer.is_participant);
  const isHost = Boolean(viewer.is_host);
  const isOpen = ["ACTIVE", "PARTIALLY_PAID"].includes(session?.status || "");

  const assignedByOthers = useMemo(() => {
    const blocked = new Set();
    const viewerUserId = Number(viewer?.user_id || 0);
    activeParticipants.forEach((participant) => {
      if (Number(participant.user_id) === viewerUserId) return;
      (participant.selected_seats || []).forEach((label) => blocked.add(String(label).toUpperCase()));
    });
    return blocked;
  }, [activeParticipants, viewer?.user_id]);

  const handleJoin = async () => {
    if (working) return;
    setWorking(true);
    setError("");
    setInfo("");
    try {
      const payload = await joinGroupBookingSession(inviteCode, {});
      if (payload?.session) setSession(payload.session);
      setInfo(payload?.message || "Joined group booking session.");
    } catch (err) {
      setError(err?.message || "Unable to join group booking session.");
    } finally {
      setWorking(false);
    }
  };

  const handleToggleSeat = (label) => {
    if (!isParticipant || !isOpen) return;
    if (assignedByOthers.has(label)) return;
    setSeatDraft((prev) => {
      const has = prev.includes(label);
      if (has) return prev.filter((item) => item !== label);
      return normalizeSeatList([...prev, label]);
    });
  };

  const handleSaveSeatSelection = async () => {
    if (!session || !isParticipant || !isOpen || working) return;
    setWorking(true);
    setError("");
    setInfo("");
    try {
      const payload = await assignGroupBookingSeats(session.id, {
        selected_seats: seatDraft,
      });
      if (payload?.session) setSession(payload.session);
      setInfo(payload?.message || "Seat assignment updated.");
    } catch (err) {
      setError(err?.message || "Unable to update seat assignment.");
    } finally {
      setWorking(false);
    }
  };

  const handleManualSplitChange = (userId, value) => {
    setManualDraft((prev) => ({
      ...prev,
      [userId]: value,
    }));
  };

  const handleSaveManualSplit = async () => {
    if (!session || !isHost || session.split_mode !== "MANUAL" || working) return;

    const allocations = activeParticipants.map((participant) => ({
      user_id: participant.user_id,
      amount: Number(manualDraft[participant.user_id] || 0),
    }));

    setWorking(true);
    setError("");
    setInfo("");
    try {
      const payload = await applyGroupManualSplit(session.id, { allocations });
      if (payload?.session) setSession(payload.session);
      setInfo(payload?.message || "Manual split saved.");
    } catch (err) {
      setError(err?.message || "Unable to save manual split.");
    } finally {
      setWorking(false);
    }
  };

  const handleParticipantPayment = async (completionStatus) => {
    if (!session || !isParticipant || !isOpen || working) return;

    setWorking(true);
    setError("");
    setInfo("");
    try {
      const initPayload = await initiateGroupBookingPayment(session.id, {
        payment_method: "ESEWA",
      });
      const paymentId = initPayload?.payment?.id;
      if (!paymentId) {
        if (initPayload?.session) setSession(initPayload.session);
        setInfo(initPayload?.message || "No pending amount for payment.");
        return;
      }

      const completionPayload = await completeGroupBookingPayment(session.id, paymentId, {
        status: completionStatus,
        transaction_id: buildTransactionId(),
      });
      if (completionPayload?.session) setSession(completionPayload.session);
      setInfo(completionPayload?.message || "Payment processed.");
    } catch (err) {
      setError(err?.message || "Unable to process payment.");
    } finally {
      setWorking(false);
    }
  };

  const handleDropOut = async () => {
    if (!session || !isParticipant || isHost || !isOpen || working) return;
    setWorking(true);
    setError("");
    setInfo("");
    try {
      const payload = await dropOutGroupBookingSession(session.id, {});
      if (payload?.session) setSession(payload.session);
      setInfo(payload?.message || "You left the session.");
    } catch (err) {
      setError(err?.message || "Unable to leave session.");
    } finally {
      setWorking(false);
    }
  };

  const handleCancel = async () => {
    if (!session || !isHost || !isOpen || working) return;
    setWorking(true);
    setError("");
    setInfo("");
    try {
      const payload = await cancelGroupBookingSession(session.id, {});
      if (payload?.session) setSession(payload.session);
      setInfo(payload?.message || "Session cancelled.");
    } catch (err) {
      setError(err?.message || "Unable to cancel session.");
    } finally {
      setWorking(false);
    }
  };

  const handleCopyInviteLink = async () => {
    if (!session?.invite_link) return;
    try {
      await navigator.clipboard.writeText(session.invite_link);
      setInfo("Invite link copied.");
    } catch {
      setInfo("Copy not supported in this browser.");
    }
  };

  if (loading) {
    return (
      <div className="gb-page">
        <div className="gb-shell">
          <p className="gb-muted">Loading group booking session...</p>
        </div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="gb-page">
        <div className="gb-shell">
          <p className="gb-error">{error || "Session not found."}</p>
          <button type="button" className="gb-btn" onClick={() => navigate("/group-booking/new")}>
            Back to Group Booking
          </button>
        </div>
      </div>
    );
  }

  const sessionSeats = normalizeSeatList(session.selected_seats || []);

  return (
    <div className="gb-page">
      <div className="gb-shell">
        <header className="gb-header gb-header-row">
          <div>
            <h1>Group Booking Session</h1>
            <p>
              {session?.show?.movie_title || "Movie"} | {session?.show?.show_date || "-"} {session?.show?.show_time || ""} | {session?.show?.hall || "-"}
            </p>
          </div>
          <div className="gb-actions">
            <button type="button" className="gb-btn" onClick={() => loadSession()} disabled={working}>
              Refresh
            </button>
            <button type="button" className="gb-btn" onClick={() => navigate("/group-booking/new")}>New Session</button>
          </div>
        </header>

        <section className="gb-card gb-highlight">
          <div className="gb-card-head">
            <h2>Invite Participants</h2>
            <span className={`gb-status gb-status-${String(session.status || "").toLowerCase()}`}>{session.status}</span>
          </div>
          <p>
            Invite code: <strong>{session.invite_code}</strong>
          </p>
          <p className="gb-mono">{session.invite_link}</p>
          <div className="gb-actions">
            <button type="button" className="gb-btn" onClick={handleCopyInviteLink}>Copy Invite Link</button>
            {!isParticipant && isOpen ? (
              <button type="button" className="gb-btn gb-btn-primary" onClick={handleJoin} disabled={working}>
                Join Session
              </button>
            ) : null}
            {isHost && isOpen ? (
              <button type="button" className="gb-btn gb-btn-danger" onClick={handleCancel} disabled={working}>
                Cancel Session
              </button>
            ) : null}
            {isParticipant && !isHost && isOpen ? (
              <button type="button" className="gb-btn gb-btn-danger" onClick={handleDropOut} disabled={working}>
                Leave Session
              </button>
            ) : null}
          </div>

          <div className="gb-progress">
            <div>
              <span>Total</span>
              <strong>{toMoney(session.total_amount)}</strong>
            </div>
            <div>
              <span>Paid</span>
              <strong>{toMoney(session.amount_paid)}</strong>
            </div>
            <div>
              <span>Remaining</span>
              <strong>{toMoney(session.amount_remaining)}</strong>
            </div>
            <div>
              <span>Expiry</span>
              <strong>{session.expires_in_seconds != null ? `${session.expires_in_seconds}s` : "-"}</strong>
            </div>
          </div>
        </section>

        {session.split_mode === "SEAT_BASED" && isParticipant ? (
          <section className="gb-card">
            <div className="gb-card-head">
              <h2>Seat Assignment</h2>
              <span className="gb-muted">Choose your seats before payment.</span>
            </div>
            <div className="gb-seat-grid">
              {sessionSeats.map((seatLabel) => {
                const blocked = assignedByOthers.has(seatLabel);
                const selected = seatDraft.includes(seatLabel);
                return (
                  <button
                    key={seatLabel}
                    type="button"
                    className={`gb-seat ${selected ? "gb-seat-selected" : ""} ${blocked ? "gb-seat-blocked" : ""}`}
                    onClick={() => handleToggleSeat(seatLabel)}
                    disabled={blocked || !isOpen}
                  >
                    {seatLabel}
                  </button>
                );
              })}
            </div>
            <div className="gb-actions">
              <button type="button" className="gb-btn gb-btn-primary" onClick={handleSaveSeatSelection} disabled={working || !isOpen}>
                Save Seat Selection
              </button>
            </div>
          </section>
        ) : null}

        {session.split_mode === "MANUAL" && isHost ? (
          <section className="gb-card">
            <div className="gb-card-head">
              <h2>Manual Split (Host Override)</h2>
              <span className="gb-muted">Total must match {toMoney(session.total_amount)}.</span>
            </div>
            <div className="gb-table-wrap">
              <table className="gb-table">
                <thead>
                  <tr>
                    <th>Participant</th>
                    <th>Amount To Pay</th>
                  </tr>
                </thead>
                <tbody>
                  {activeParticipants.map((participant) => (
                    <tr key={participant.id}>
                      <td>{participant.name}</td>
                      <td>
                        <input
                          type="number"
                          min="0"
                          step="0.01"
                          value={manualDraft[participant.user_id] || "0.00"}
                          onChange={(event) => handleManualSplitChange(participant.user_id, event.target.value)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="gb-actions">
              <button type="button" className="gb-btn gb-btn-primary" onClick={handleSaveManualSplit} disabled={working || !isOpen}>
                Save Manual Split
              </button>
            </div>
          </section>
        ) : null}

        <section className="gb-card">
          <div className="gb-card-head">
            <h2>Participants</h2>
            <span className="gb-muted">Split mode: {session.split_mode}</span>
          </div>
          <div className="gb-table-wrap">
            <table className="gb-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Seats</th>
                  <th>To Pay</th>
                  <th>Paid</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {participants.map((participant) => (
                  <tr key={participant.id}>
                    <td>
                      {participant.name}
                      {participant.is_host ? " (Host)" : ""}
                    </td>
                    <td>{(participant.selected_seats || []).join(", ") || "-"}</td>
                    <td>{toMoney(participant.amount_to_pay)}</td>
                    <td>{toMoney(participant.amount_paid)}</td>
                    <td>{participant.payment_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {isParticipant && isOpen ? (
            <div className="gb-actions">
              <button
                type="button"
                className="gb-btn gb-btn-primary"
                onClick={() => handleParticipantPayment("SUCCESS")}
                disabled={working}
              >
                Pay My Share
              </button>
              <button
                type="button"
                className="gb-btn"
                onClick={() => handleParticipantPayment("FAILED")}
                disabled={working}
              >
                Simulate Payment Failure
              </button>
            </div>
          ) : null}
        </section>

        {session.status === "COMPLETED" ? (
          <section className="gb-card gb-highlight">
            <h2>Group Booking Confirmed</h2>
            <p>All participants have paid. Individual booking and ticket records were generated.</p>
            {!session.bookings?.length ? (
              <p className="gb-muted">No booking records found in session payload.</p>
            ) : (
              <div className="gb-table-wrap">
                <table className="gb-table">
                  <thead>
                    <tr>
                      <th>User ID</th>
                      <th>Booking ID</th>
                      <th>Seats</th>
                      <th>Ticket Reference</th>
                    </tr>
                  </thead>
                  <tbody>
                    {session.bookings.map((item) => (
                      <tr key={`${item.booking_id}-${item.user_id}`}>
                        <td>{item.user_id}</td>
                        <td>{item.booking_id}</td>
                        <td>{Array.isArray(item.seats) ? item.seats.join(", ") : "-"}</td>
                        <td>{item.ticket_reference || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        ) : null}

        {error ? <p className="gb-error">{error}</p> : null}
        {info ? <p className="gb-info">{info}</p> : null}
      </div>
    </div>
  );
}
