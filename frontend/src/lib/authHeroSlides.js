import { getComingSoon, getNowShowing, resolveMoviesByShowListing } from "./showUtils";

const MAX_AUTH_HERO_SLIDES = 10;
const DEFAULT_NOW_DESCRIPTION =
  "Discover the latest shows, compare vendors, and secure your seats with a single tap.";
const DEFAULT_SOON_DESCRIPTION =
  "Upcoming releases are live now. Create your account and be ready to book first.";

export function buildAuthHeroSlides(movies, showtimes, options = {}) {
  const movieList = Array.isArray(movies) ? movies : [];
  const showList = Array.isArray(showtimes) ? showtimes : [];

  if (!movieList.length) return [];

  const nowLimit = toPositiveNumber(options.nowLimit, 6);
  const soonLimit = toPositiveNumber(options.soonLimit, 6);
  const maxSlides = toPositiveNumber(options.maxSlides, MAX_AUTH_HERO_SLIDES);

  let nowShowingMovies = [];
  let comingSoonMovies = [];

  if (showList.length) {
    const buckets = resolveMoviesByShowListing(movieList, showList);
    nowShowingMovies = Array.isArray(buckets?.nowShowing) ? buckets.nowShowing : [];
    comingSoonMovies = Array.isArray(buckets?.comingSoon) ? buckets.comingSoon : [];
  }

  if (!nowShowingMovies.length) {
    nowShowingMovies = getNowShowing(movieList, nowLimit);
  }
  if (!comingSoonMovies.length) {
    comingSoonMovies = getComingSoon(movieList, soonLimit);
  }

  const slides = [
    ...nowShowingMovies.map((movie, index) =>
      toAuthHeroSlide(movie, "Now Showing", DEFAULT_NOW_DESCRIPTION, index)
    ),
    ...comingSoonMovies.map((movie, index) =>
      toAuthHeroSlide(movie, "Coming Soon", DEFAULT_SOON_DESCRIPTION, index)
    ),
  ];

  const deduped = [];
  const seen = new Set();
  for (const slide of slides) {
    if (!slide) continue;
    const dedupeKey = `${slide.badge}:${slide.movieKey}`;
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);
    deduped.push(slide);
    if (deduped.length >= maxSlides) break;
  }

  return deduped;
}

export function resolveMoviePoster(movie) {
  return (
    movie?.posterImage ||
    movie?.poster_image ||
    movie?.poster ||
    movie?.posterUrl ||
    movie?.poster_url ||
    ""
  );
}

function toAuthHeroSlide(movie, badge, defaultDescription, index) {
  const image = resolveMoviePoster(movie);
  if (!image) return null;

  const movieId = movie?.id ?? movie?._id ?? `${badge.toLowerCase().replace(/\s+/g, "-")}-${index}`;
  const title = String(movie?.title || movie?.name || "").trim();
  const description = String(
    movie?.shortDescription || movie?.short_description || movie?.description || movie?.synopsis || ""
  ).trim();

  return {
    id: `${badge.toLowerCase().replace(/\s+/g, "-")}-${movieId}`,
    movieKey: String(movieId),
    badge,
    title: title || (badge === "Coming Soon" ? "Upcoming Releases" : "Now Showing"),
    description: description || defaultDescription,
    image,
  };
}

function toPositiveNumber(value, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return fallback;
  return Math.floor(parsed);
}
