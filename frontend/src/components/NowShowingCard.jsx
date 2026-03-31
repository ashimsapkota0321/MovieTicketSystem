import React from "react";
import gharjwai from "../images/gharjwai.jpg";
import { buildMetaLine, isAdultRating, toText } from "../lib/showUtils";

export default function NowShowingCard({ movie, onBuy }) {
  const title = movie?.title || movie?.name || "Movie Name";
  const poster =
    movie?.posterImage ||
    movie?.poster_image ||
    movie?.poster ||
    movie?.posterUrl ||
    movie?.poster_url ||
    movie?.image ||
    movie?.bannerImage ||
    movie?.banner_image ||
    gharjwai;
  const ratingLabel =
    toText(movie?.censor || movie?.rating || movie?.certificate || movie?.classification) || "PG";
  const metaLine = buildMetaLine(movie);
  const badgeClass = isAdultRating(ratingLabel) ? "ns-cardBadge ns-cardBadgeAdult" : "ns-cardBadge";

  const handleKeyDown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onBuy?.();
    }
  };

  return (
    <div
      className="ns-card"
      role="button"
      tabIndex={0}
      onClick={onBuy}
      onKeyDown={handleKeyDown}
    >
      <div className="ns-cardPoster">
        <img src={poster} alt={title} loading="lazy" decoding="async" />
        <div className={badgeClass}>{ratingLabel}</div>
      </div>

      <div className="ns-cardInfo">
        <div className="ns-cardTitle">{title}</div>
        <div className="ns-cardMeta">{metaLine}</div>
      </div>
    </div>
  );
}
