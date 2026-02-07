import React from "react";
import { useNavigate } from "react-router-dom";
import gharjwai from "../images/gharjwai.jpg";

export default function MovieCard({ movie }) {
  const navigate = useNavigate();
  const title = movie?.title || movie?.name || "Movie Name";
  const poster = movie?.poster || movie?.posterUrl || movie?.image || gharjwai;
  const id = movie?._id || movie?.id || encodeURIComponent(title);

  return (
    <div className="wf2-card" onClick={() => navigate(`/movie/${id}`)} style={{ cursor: "pointer" }}>
      <div className="wf2-cardPoster">
        <img src={poster} alt={title} />
      </div>

      <div className="wf2-cardBody">
        <div className="wf2-cardTitle">{title}</div>
        <div className="wf2-cardSub">Date - Category - Duration</div>

        <div className="wf2-cardFoot">
          <button
            className="wf2-btn wf2-btnGhost wf2-btnPill wf2-btnSm"
            onClick={(e) => {
              e.stopPropagation();
              navigate(`/movie/${id}`);
            }}
          >
            Buy Ticket
          </button>

          <div className="wf2-rating">★ <span>Rating</span></div>
        </div>
      </div>
    </div>
  );
}
