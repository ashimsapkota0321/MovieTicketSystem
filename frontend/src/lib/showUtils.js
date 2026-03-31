export function formatDateLabel(value) {
  if (!value) return "";
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) {
    return date.toLocaleDateString("en-GB", {
      day: "2-digit",
      month: "short",
      year: "numeric",
    });
  }
  return String(value);
}

export function toText(value) {
  if (!value) return "";
  if (Array.isArray(value)) return value.filter(Boolean).join(", ");
  return String(value);
}

export function getMovieRatingLabel(movie) {
  return toText(
    movie?.certificate ||
      movie?.classification ||
      movie?.censor ||
      movie?.ageRating ||
      movie?.rating
  );
}

export function buildMetaLine(movie) {
  const language = toText(movie?.language || movie?.lang);
  const genre = toText(movie?.genre || movie?.category || movie?.type);
  const parts = [language, genre].filter(Boolean);
  return parts.length ? parts.join(" | ") : "Nepali | Drama";
}

export function isAdultRating(label) {
  const value = String(label || "").trim().toLowerCase();
  if (!value) return false;
  if (value.includes("adult") || value.includes("18") || value.includes("a-rated")) {
    return true;
  }

  // Match token "A" as a standalone certification (e.g. "A", "[A]", "Rated A").
  const compact = String(label || "").trim().toUpperCase();
  return /(?:^|[^A-Z])A(?:$|[^A-Z])/.test(compact);
}

export function isAdultMovie(movie) {
  return isAdultRating(getMovieRatingLabel(movie));
}

export function isNowShowingStatus(status) {
  const value = normalizeStatusText(status);
  return (
    value.includes("now") ||
    value.includes("showing") ||
    value === "open" ||
    value === "scheduled"
  );
}

export function isComingSoonStatus(status) {
  const value = normalizeStatusText(status);
  return value.includes("coming") || value.includes("soon") || value.includes("premiere");
}

export function getNowShowing(items, limit) {
  if (!Array.isArray(items)) return [];
  const filtered = items.filter((item) =>
    isNowShowingStatus(item?.listingStatus || item?.status)
  );
  if (typeof limit === "number") {
    const base = filtered.length ? filtered : items.filter(Boolean);
    return base.slice(0, Math.max(0, limit));
  }
  if (filtered.length) return filtered;
  return items.filter(Boolean).slice(0, 6);
}

export function getComingSoon(items, limit) {
  if (!Array.isArray(items)) return [];
  const filtered = items.filter((item) =>
    isComingSoonStatus(item?.listingStatus || item?.status)
  );
  if (typeof limit === "number") {
    const base = filtered.length ? filtered : items.filter(Boolean).slice(6);
    return base.slice(0, Math.max(0, limit));
  }
  if (filtered.length) return filtered;
  return items.filter(Boolean).slice(6, 12);
}

export function resolveMoviesByShowListing(movies, showtimes) {
  const movieList = Array.isArray(movies) ? movies : [];
  const showList = Array.isArray(showtimes) ? showtimes : [];
  if (!movieList.length || !showList.length) {
    return { nowShowing: [], comingSoon: [] };
  }

  const movieById = new Map();
  movieList.forEach((movie) => {
    const key = normalizeId(movie?.id ?? movie?._id);
    if (!key) return;
    if (!movieById.has(key)) movieById.set(key, movie);
  });

  const nowIds = [];
  const soonIds = [];
  const nowSet = new Set();
  const soonSet = new Set();

  showList.forEach((show) => {
    const movieId = normalizeId(show?.movieId ?? show?.movie_id ?? show?.movie);
    if (!movieId || !movieById.has(movieId)) return;

    const listing =
      show?.listingStatus ??
      show?.listing_status ??
      show?.status ??
      "";

    if (isComingSoonStatus(listing)) {
      if (!soonSet.has(movieId)) {
        soonSet.add(movieId);
        soonIds.push(movieId);
      }
      return;
    }

    if (isNowShowingStatus(listing)) {
      if (!nowSet.has(movieId)) {
        nowSet.add(movieId);
        nowIds.push(movieId);
      }
      return;
    }

    if (!nowSet.has(movieId)) {
      nowSet.add(movieId);
      nowIds.push(movieId);
    }
  });

  const filteredSoonIds = soonIds.filter((movieId) => !nowSet.has(movieId));
  return {
    nowShowing: nowIds.map((movieId) => movieById.get(movieId)).filter(Boolean),
    comingSoon: filteredSoonIds.map((movieId) => movieById.get(movieId)).filter(Boolean),
  };
}

function normalizeStatusText(status) {
  return String(status || "")
    .toLowerCase()
    .replace(/[_-]+/g, " ")
    .trim();
}

function normalizeId(value) {
  return String(value ?? "").trim();
}
