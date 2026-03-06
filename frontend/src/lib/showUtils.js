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

export function buildMetaLine(movie) {
  const language = toText(movie?.language || movie?.lang);
  const genre = toText(movie?.genre || movie?.category || movie?.type);
  const parts = [language, genre].filter(Boolean);
  return parts.length ? parts.join(" | ") : "Nepali | Drama";
}

export function isAdultRating(label) {
  const value = String(label || "").toLowerCase();
  return value.includes("adult") || value.includes("18");
}

export function isNowShowingStatus(status) {
  const value = String(status || "").toLowerCase();
  return value.includes("now") || value.includes("showing");
}

export function isComingSoonStatus(status) {
  const value = String(status || "").toLowerCase();
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
