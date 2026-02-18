import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, Play } from "lucide-react";
import "../css/seatSelection.css";

import { useAppContext } from "../context/Appcontext";
import gharjwai from "../images/gharjwai.jpg";
import avengers from "../images/avengers.jpg";
import degreemaila from "../images/degreemaila.jpg";
import balidan from "../images/balidan.jpg";

const seatGroups = [
  { label: "VIP", rows: ["A"] },
  { label: "Premium", rows: ["B", "C", "D"] },
  { label: "Executive", rows: ["E", "F", "G"] },
  { label: "Normal", rows: ["H", "I", "J"] },
];
const seatCols = Array.from({ length: 15 }, (_, i) => i + 1);
const MAX_SELECTION = 5;

const reservedSeats = new Set();
const soldSeats = new Set();
const unavailableSeats = new Set();

export default function SeatSelection() {
  const navigate = useNavigate();
  const ctx = safeUseAppContext();
  const shows = ctx?.movies ?? ctx?.shows ?? fallbackShows;
  const movie = useMemo(() => shows?.[0] ?? fallbackShows[0], [shows]);
  const [selectedSeats, setSelectedSeats] = useState([]);
  const [toastMessage, setToastMessage] = useState("");
  const [toastOpen, setToastOpen] = useState(false);
  const [toastVisible, setToastVisible] = useState(false);
  const toastTimerRef = useRef(null);
  const toastHideRef = useRef(null);
  const [ticketCounts, setTicketCounts] = useState({ senior: 0, child: 0 });

  const title = movie?.title || movie?.name || "Hami Teen Bhai";
  const poster = movie?.poster || movie?.posterUrl || movie?.image || gharjwai;
  const seatSubtitle = "2h 10m | Action, Comedy | May 2018 | UA 13+";
  const totalSeats = selectedSeats.length;
  const adultCount = Math.max(totalSeats - ticketCounts.senior - ticketCounts.child, 0);
  const prices = { adult: 250, senior: 200, child: 150 };
  const totalPrice =
    adultCount * prices.adult +
    ticketCounts.senior * prices.senior +
    ticketCounts.child * prices.child;
  const basePrice = totalSeats * prices.adult;
  const discount = Math.max(basePrice - totalPrice, 0);

  const dismissToast = () => {
    setToastOpen(false);
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
      toastTimerRef.current = null;
    }
    if (toastHideRef.current) {
      clearTimeout(toastHideRef.current);
    }
    toastHideRef.current = setTimeout(() => {
      setToastVisible(false);
    }, 240);
  };

  const showToast = (message) => {
    setToastMessage(message);
    setToastVisible(true);
    if (toastHideRef.current) {
      clearTimeout(toastHideRef.current);
      toastHideRef.current = null;
    }
    requestAnimationFrame(() => setToastOpen(true));
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = setTimeout(() => {
      dismissToast();
    }, 3000);
  };

  useEffect(() => () => {
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
    }
    if (toastHideRef.current) {
      clearTimeout(toastHideRef.current);
    }
  }, []);

  useEffect(() => {
    if (!toastVisible) return;

    const handleScroll = () => {
      dismissToast();
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [toastVisible]);

  useEffect(() => {
    setTicketCounts((prev) => {
      if (totalSeats === 0) {
        return { senior: 0, child: 0 };
      }
      const senior = Math.min(prev.senior, totalSeats);
      const child = Math.min(prev.child, totalSeats - senior);
      return { senior, child };
    });
  }, [totalSeats]);

  const toggleSeat = (key) => {
    if (reservedSeats.has(key) || soldSeats.has(key) || unavailableSeats.has(key)) {
      return;
    }

    if (selectedSeats.includes(key)) {
      setSelectedSeats(selectedSeats.filter((seat) => seat !== key));
      return;
    }

    if (selectedSeats.length >= MAX_SELECTION) {
      showToast(`You can book upto ${MAX_SELECTION} seats`);
      return;
    }

    setSelectedSeats([...selectedSeats, key]);
  };

  const increaseCount = (type) => {
    if (totalSeats === 0) {
      showToast("Select seats first.");
      return;
    }

    if (type === "adult") {
      if (ticketCounts.senior > 0) {
        setTicketCounts((prev) => ({ ...prev, senior: prev.senior - 1 }));
        return;
      }
      if (ticketCounts.child > 0) {
        setTicketCounts((prev) => ({ ...prev, child: prev.child - 1 }));
      }
      return;
    }

    if (adultCount <= 0) {
      showToast("All seats are already allocated.");
      return;
    }

    setTicketCounts((prev) => ({ ...prev, [type]: prev[type] + 1 }));
  };

  const decreaseCount = (type) => {
    if (type === "adult") {
      return;
    }

    if (ticketCounts[type] <= 0) {
      return;
    }

    setTicketCounts((prev) => ({ ...prev, [type]: prev[type] - 1 }));
  };

  const renderSelectedSeats = () => {
    if (selectedSeats.length) {
      return selectedSeats.map((seat) => (
        <span className="seat-pill" key={seat}>
          {seat}
        </span>
      ));
    }

    return <span className="seat-empty">Tap seats to add up to {MAX_SELECTION}.</span>;
  };

  const toastMarkup =
    toastVisible && typeof document !== "undefined"
      ? createPortal(
          <div
            className={`seat-toast ${toastOpen ? "seat-toast--show" : ""}`}
            role="status"
            aria-live="polite"
          >
            <span className="seat-toastText">{toastMessage}</span>
            <button
              className="seat-toastClose"
              type="button"
              onClick={dismissToast}
              aria-label="Dismiss"
            >
              x
            </button>
          </div>,
          document.body
        )
      : null;

  return (
    <div className="seat-page">
      {toastMarkup}
      <div className="seat-wrap">
        <div className="seat-header">
          <button
            className="seat-backBtn"
            type="button"
            onClick={() => navigate(-1)}
            aria-label="Go back"
          >
            <ChevronLeft size={18} />
          </button>
          <div>
            <h2 className="seat-title">{title}</h2>
            <p className="seat-subtitle">{seatSubtitle}</p>
          </div>
        </div>

        <div className="seat-top">
          <div className="seat-card">
            <div className="seat-poster">
              <img src={poster} alt={title} />
              <button className="seat-playBtn" type="button" aria-label="Play trailer">
                <Play size={18} />
              </button>
            </div>
          </div>

          <div className="seat-card">
            <div className="seat-cardTitle">QFX Cinemas</div>
            <div className="seat-cardSub">Shows Today, Seat Challenge</div>
            <div className="seat-showtimes">
              {["10:00 AM", "12:30 PM", "2:00 PM", "6:30 PM", "9:00 PM", "10:30 PM"].map((time) => (
                <button className="seat-timeChip" type="button" key={time}>
                  {time}
                </button>
              ))}
            </div>
          </div>

          <div className="seat-card">
            <div className="seat-cardTitle">Movie Details</div>
            <div className="seat-detailsList">
              <div>Language: <span>Nepali</span></div>
              <div>Genre: <span>Action, Comedy</span></div>
              <div>Censor: <span>UA 13+</span></div>
              <div>Starring: <span>Rajesh Hamal, Nikhil Upreti, Shree Krishna</span></div>
              <div>Director: <span>Shive Regrin</span></div>
            </div>
          </div>
        </div>

        <div className="seat-layout">
          <div>
            <div className="seat-mapHeader">
              <div className="seat-mapLabel">Select Your Seat</div>
              <div className="seat-screen">
                <span>SCREEN</span>
                <div className="seat-curve" />
              </div>
            </div>

            <div className="seat-mapCard">
              <div className="seat-map" style={{ "--seat-count": seatCols.length }}>
                {seatGroups.map((group) => (
                  <div className="seat-group" key={group.label}>
                    <div className="seat-groupTitle">{group.label}</div>
                    <div className="seat-groupRows">
                      {group.rows.map((row) => (
                        <div className="seat-row" key={row}>
                          <div className="seat-rowLabel">{row}</div>
                          <div className="seat-rowSeats">
                            {seatCols.map((col) => {
                              const key = `${row}${col}`;
                              const status = getSeatStatus(key, selectedSeats);
                              const isBlocked =
                                status === "seat--reserved" ||
                                status === "seat--sold" ||
                                status === "seat--unavailable";
                              return (
                                <button
                                  type="button"
                                  key={key}
                                  className={`seat ${status}`}
                                  aria-label={`Seat ${key}`}
                                  aria-pressed={status === "seat--selected"}
                                  disabled={isBlocked}
                                  onClick={() => toggleSeat(key)}
                                >
                                  {key}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}

                <div className="seat-colLabels">
                  <div className="seat-colSpacer" />
                  {seatCols.map((col) => (
                    <div className="seat-colLabel" key={`col-${col}`}>
                      {col}
                    </div>
                  ))}
                </div>
              </div>

              <div className="seat-metaRow">
                <div className="seat-selectedInfo">
                  <strong>{selectedSeats.length} Selected Seats</strong>
                  <span className="seat-limit">Max {MAX_SELECTION}</span>
                </div>
                <div className="seat-selectedList">{renderSelectedSeats()}</div>
              </div>

              <div className="seat-legend">
                <span className="seat-legendItem">
                  <span className="seat-legendBox available" /> Available
                </span>
                <span className="seat-legendItem">
                  <span className="seat-legendBox selected" /> Selected
                </span>
                <span className="seat-legendItem">
                  <span className="seat-legendBox reserved" /> Reserved
                </span>
                <span className="seat-legendItem">
                  <span className="seat-legendBox sold" /> Sold Out
                </span>
                <span className="seat-legendItem">
                  <span className="seat-legendBox unavailable" /> Unavailable
                </span>
              </div>
            </div>
          </div>

          <div className="seat-summary">
            <div className="seat-summaryTitle">Selected Seats</div>
            <div className="seat-summarySeats">{renderSelectedSeats()}</div>

            <div className="seat-priceRow">
              <span>Adult <span className="seat-muted">Npr 250</span></span>
              <div className="seat-counter">
                <button className="seat-counterBtn" type="button" disabled>
                  -
                </button>
                <span>{adultCount}</span>
                <button
                  className="seat-counterBtn"
                  type="button"
                  onClick={() => increaseCount("adult")}
                  disabled={ticketCounts.senior === 0 && ticketCounts.child === 0}
                >
                  +
                </button>
              </div>
            </div>

            <div className="seat-priceRow">
              <span>Senior <span className="seat-muted">Npr 200</span></span>
              <div className="seat-counter">
                <button
                  className="seat-counterBtn"
                  type="button"
                  onClick={() => decreaseCount("senior")}
                  disabled={ticketCounts.senior === 0}
                >
                  -
                </button>
                <span>{ticketCounts.senior}</span>
                <button
                  className="seat-counterBtn"
                  type="button"
                  onClick={() => increaseCount("senior")}
                  disabled={adultCount === 0}
                >
                  +
                </button>
              </div>
            </div>

            <div className="seat-priceRow">
              <span>Child <span className="seat-muted">Npr 150</span></span>
              <div className="seat-counter">
                <button
                  className="seat-counterBtn"
                  type="button"
                  onClick={() => decreaseCount("child")}
                  disabled={ticketCounts.child === 0}
                >
                  -
                </button>
                <span>{ticketCounts.child}</span>
                <button
                  className="seat-counterBtn"
                  type="button"
                  onClick={() => increaseCount("child")}
                  disabled={adultCount === 0}
                >
                  +
                </button>
              </div>
            </div>

            {discount > 0 ? (
              <div className="seat-priceRow seat-discountRow">
                <span>Discount</span>
                <span>-Npr {discount}</span>
              </div>
            ) : null}

            <div className="seat-total">
              <span>Total Payment:</span>
              <span>Npr {totalPrice}</span>
            </div>

            <button
              className="seat-payBtn"
              type="button"
              onClick={() => navigate("/food")}
              disabled={totalSeats === 0}
            >
              Proceed
            </button>
            <button
              className="seat-cancelBtn"
              type="button"
              onClick={() => {
                setSelectedSeats([]);
                setTicketCounts({ senior: 0, child: 0 });
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function getSeatStatus(key, selectedSeats) {
  if (selectedSeats.includes(key)) return "seat--selected";
  if (reservedSeats.has(key)) return "seat--reserved";
  if (soldSeats.has(key)) return "seat--sold";
  if (unavailableSeats.has(key)) return "seat--unavailable";
  return "seat--available";
}

function safeUseAppContext() {
  try {
    return useAppContext?.();
  } catch {
    return null;
  }
}

const fallbackShows = [
  { _id: "1", title: "Hami Teen Bhai", poster: gharjwai },
  { _id: "2", title: "Avengers", poster: avengers },
  { _id: "3", title: "Degree Maila", poster: degreemaila },
  { _id: "4", title: "Balidan", poster: balidan },
];
