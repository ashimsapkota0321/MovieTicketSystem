import React, { useMemo } from "react";
import { Play } from "lucide-react";
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

const selectedSeats = [];
const reservedSeats = new Set();
const soldSeats = new Set();
const unavailableSeats = new Set();

export default function SeatSelection() {
  const ctx = safeUseAppContext();
  const shows = ctx?.shows ?? fallbackShows;
  const movie = useMemo(() => shows?.[0] ?? fallbackShows[0], [shows]);

  const title = movie?.title || movie?.name || "Hami Teen Bhai";
  const poster = movie?.poster || movie?.posterUrl || movie?.image || gharjwai;

  return (
    <div className="seat-page">
      <div className="seat-wrap">
        <h2 className="seat-title">{title}</h2>
        <p className="seat-subtitle">
          2h 10m | Action, Comedy | May 2018 | UA 13+
        </p>

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
              <div className="seat-curve" />
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
                              const status = getSeatStatus(key);
                              return (
                                <button
                                  type="button"
                                  key={key}
                                  className={`seat ${status}`}
                                  aria-label={`Seat ${key}`}
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
                </div>
                <div className="seat-selectedList">{selectedSeats.join(", ")}</div>
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
            <div className="seat-summarySeats">{selectedSeats.join(", ")}</div>

            <div className="seat-priceRow">
              <span>Adult <span className="seat-muted">Npr 250</span></span>
              <div className="seat-counter">
                <button className="seat-counterBtn" type="button">-</button>
                <span>1</span>
                <button className="seat-counterBtn" type="button">+</button>
              </div>
            </div>

            <div className="seat-priceRow">
              <span>Senior <span className="seat-muted">Npr 200</span></span>
              <div className="seat-counter">
                <button className="seat-counterBtn" type="button">-</button>
                <span>1</span>
                <button className="seat-counterBtn" type="button">+</button>
              </div>
            </div>

            <div className="seat-priceRow">
              <span>Child <span className="seat-muted">Npr 150</span></span>
              <div className="seat-counter">
                <button className="seat-counterBtn" type="button">-</button>
                <span>1</span>
                <button className="seat-counterBtn" type="button">+</button>
              </div>
            </div>

            <div className="seat-total">
              <span>Total Payment:</span>
              <span>Npr 900</span>
            </div>

            <button className="seat-payBtn" type="button">Pay</button>
            <button className="seat-cancelBtn" type="button">Cancel</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function getSeatStatus(key) {
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
