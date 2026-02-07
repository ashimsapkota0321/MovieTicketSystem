import React from "react";
import { useNavigate } from "react-router-dom";
import "../css/cinemas.css";
import { cinemaVendors } from "../lib/cinemas";

export default function Cinemas() {
  const navigate = useNavigate();

  return (
    <div className="wf2-page cinemas-page">
      <div className="wf2-container cinemas-wrap">
        <div className="cinemas-head">
          <div>
            <h2 className="cinemas-title">Choose Your Cinema</h2>
            <p className="cinemas-sub">
              Pick a cinema vendor to see showtimes for that hall.
            </p>
          </div>
        </div>

        <div className="cinemas-grid">
          {cinemaVendors.map((vendor) => (
            <button
              key={vendor.slug}
              className="cinema-card"
              type="button"
              style={{ "--cinema-accent": vendor.accent }}
              onClick={() => navigate(`/cinemas/${vendor.slug}`)}
            >
              <div className="cinema-cardTop">
                <div className="cinema-mark">{vendor.short}</div>
                <span className="cinema-count">{vendor.locations.length} locations</span>
              </div>
              <div className="cinema-name">{vendor.name}</div>
              <div className="cinema-locations">
                {vendor.locations.slice(0, 3).join(" · ")}
              </div>
              <div className="cinema-action">View schedules</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
