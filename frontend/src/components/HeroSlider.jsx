import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import api from "../api/api";
import "../css/hero-slider.css";

const AUTO_PLAY_MS = 5000;
const DRAG_THRESHOLD_RATIO = 0.22;
const DRAG_DISTANCE_PX = 28;

function parseYear(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.getFullYear();
}

function mapBannerToSlide(banner) {
  if (!banner) return null;
  const movie = banner.movie || null;
  const image =
    banner.image ||
    movie?.bannerImage ||
    movie?.posterImage ||
    movie?.posterUrl ||
    movie?.poster_url ||
    null;
  if (!image && !movie) return null;

  const isMovie = banner.banner_type === "MOVIE" && movie?.id;
  return {
    id: banner.id,
    slide_type: isMovie ? "MOVIE" : "PROMO",
    movie_id: isMovie ? movie.id : null,
    title: movie?.title || "",
    subtitle: "",
    badge_text: isMovie ? "Now Showing" : "",
    description: movie?.shortDescription || movie?.description || "",
    image,
    genre: movie?.genre || "",
    year: parseYear(movie?.releaseDate),
    duration: movie?.duration || "",
    cta_type: isMovie ? "MOVIE_DETAIL" : null,
    cta_text: isMovie ? "Buy Ticket" : null,
    external_url: null,
  };
}

export default function HeroSlider({ page = "home" }) {
  const navigate = useNavigate();
  const heroRef = useRef(null);
  const trackRef = useRef(null);
  const dragState = useRef({
    active: false,
    pointerId: null,
    startX: 0,
    lastX: 0,
    moved: false,
  });
  const [slides, setSlides] = useState([]);
  // Track index is used for the infinite-loop track. When there are 2+ slides:
  // loopSlides = [lastClone, ...slides, firstClone] and trackIndex starts at 1.
  const [trackIndex, setTrackIndex] = useState(0);
  const [transitionEnabled, setTransitionEnabled] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [dragOffset, setDragOffset] = useState(0);
  const autoRef = useRef(null);
  const wheelLock = useRef(0);
  const paused = isDragging;
  const canSlide = slides.length > 1;

  useEffect(() => {
    let mounted = true;
    const loadSlides = async () => {
      try {
        const bannerResponse = await api.get("/api/banners/active/", {
          params: page ? { page } : undefined,
        });
        const banners = bannerResponse?.data?.banners || [];
        const bannerSlides = banners
          .map((banner) => mapBannerToSlide(banner))
          .filter(Boolean);
        if (!mounted) return;
        if (bannerSlides.length) {
          setSlides(bannerSlides);
          return;
        }
      } catch {
        if (!mounted) return;
      }

      try {
        const response = await api.get("/api/home/now-showing-slides/");
        const nextSlides = response?.data?.slides || [];
        if (!mounted) return;
        setSlides(nextSlides);
      } catch {
        if (!mounted) return;
        setSlides([]);
      }
    };
    loadSlides();
    return () => {
      mounted = false;
    };
  }, [page]);

  useEffect(() => {
    // Reset to the first slide whenever the slide list changes.
    setTransitionEnabled(false);
    setTrackIndex(slides.length > 1 ? 1 : 0);
    const id = window.requestAnimationFrame(() => setTransitionEnabled(true));
    return () => window.cancelAnimationFrame(id);
  }, [slides]);

  useEffect(() => {
    if (!slides.length || !canSlide || paused) return;
    autoRef.current = window.setInterval(() => {
      // Always advance to the next slide so autoplay moves left continuously.
      setTrackIndex((prev) => Math.min(slides.length + 1, prev + 1));
    }, AUTO_PLAY_MS);
    return () => window.clearInterval(autoRef.current);
  }, [slides.length, canSlide, paused]);

  const handlePrev = () => {
    if (!canSlide) return;
    setTrackIndex((prev) => Math.max(0, prev - 1));
  };

  const handleNext = () => {
    if (!canSlide) return;
    setTrackIndex((prev) => Math.min(slides.length + 1, prev + 1));
  };

  const moveToDot = (targetIndex) => {
    if (!canSlide || !slides.length) return;
    const currentIndex = activeRealIndex;
    const total = slides.length;
    const safeTarget = Math.max(0, Math.min(total - 1, targetIndex));
    if (safeTarget === currentIndex) return;

    const forwardSteps =
      safeTarget >= currentIndex
        ? safeTarget - currentIndex
        : total - currentIndex + safeTarget;
    const backwardSteps =
      currentIndex >= safeTarget
        ? currentIndex - safeTarget
        : currentIndex + (total - safeTarget);

    if (backwardSteps < forwardSteps) {
      setTrackIndex((prev) => Math.max(0, prev - backwardSteps));
      return;
    }
    setTrackIndex((prev) => Math.min(slides.length + 1, prev + forwardSteps));
  };

  const handleCta = (slide) => {
    if (!slide) return;
    if (slide.cta_type === "EXTERNAL_LINK") {
      if (slide.external_url) {
        window.open(slide.external_url, "_blank", "noopener,noreferrer");
      }
      return;
    }
    if (!slide.movie_id) return;
    if (slide.cta_type === "BOOK_NOW") {
      navigate(`/booking?movieId=${slide.movie_id}`);
      return;
    }
    navigate(`/movie/${slide.movie_id}`);
  };

  const loopSlides = useMemo(() => {
    if (!canSlide) return slides;
    const first = slides[0];
    const last = slides[slides.length - 1];
    return [last, ...slides, first];
  }, [slides, canSlide]);

  const activeRealIndex = useMemo(() => {
    if (!slides.length) return 0;
    if (!canSlide) return 0;
    return (trackIndex - 1 + slides.length) % slides.length;
  }, [slides.length, canSlide, trackIndex]);

  const slideTrackStyle = useMemo(
    () => ({
      transform: `translate3d(calc(-${trackIndex * 100}% + ${dragOffset}px), 0, 0)`,
      transition: isDragging || !transitionEnabled ? "none" : undefined,
    }),
    [trackIndex, dragOffset, isDragging, transitionEnabled]
  );

  const handleTrackTransitionEnd = (event) => {
    if (!canSlide) return;
    if (event && event.target !== event.currentTarget) return;
    if (event && event.propertyName !== "transform") return;

    // Seamless infinite loop: when we reach clones, snap to the matching real slide.
    const max = slides.length + 1;
    if (trackIndex !== 0 && trackIndex !== max) return;

    setTransitionEnabled(false);
    setDragOffset(0);
    setTrackIndex(trackIndex === 0 ? slides.length : 1);
    // Wait an extra frame so the clone->real index jump paints with no transition.
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        setTransitionEnabled(true);
      });
    });
  };

  const startDrag = (event) => {
    if (!canSlide) return;
    if (event.button !== undefined && event.button !== 0) return;
    const target = event.target;
    if (target && target.closest) {
      if (target.closest("button, a, input, select, textarea")) return;
    }
    dragState.current = {
      active: true,
      pointerId: event.pointerId,
      startX: event.clientX,
      lastX: event.clientX,
      moved: false,
    };
    setIsDragging(true);
    setDragOffset(0);
    if (event.currentTarget?.setPointerCapture) {
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {
        // ignore capture failures
      }
    }
  };

  const moveDrag = (event) => {
    if (!dragState.current.active) return;
    const width = heroRef.current?.clientWidth || 1;
    const rawDelta = event.clientX - dragState.current.startX;
    if (!dragState.current.moved && Math.abs(rawDelta) > 6) {
      dragState.current.moved = true;
    }
    const maxDelta = Math.max(20, width * 0.9);
    const clamped = Math.max(-maxDelta, Math.min(maxDelta, rawDelta));
    dragState.current.lastX = event.clientX;
    setDragOffset(clamped);
    if (dragState.current.moved) {
      event.preventDefault();
    }
  };

  const endDrag = (event) => {
    if (!dragState.current.active) return;
    const width = heroRef.current?.clientWidth || 1;
    const threshold = Math.max(DRAG_DISTANCE_PX, width * DRAG_THRESHOLD_RATIO);
    const delta =
      (event?.clientX ?? dragState.current.lastX) - dragState.current.startX;

    dragState.current.active = false;
    dragState.current.pointerId = null;
    dragState.current.moved = false;

    setIsDragging(false);
    setDragOffset(0);

    if (Math.abs(delta) < threshold) return;

    // Manual gesture controls direction:
    // swipe right => previous slide (moves banner right), swipe left => next slide.
    if (delta > 0) {
      handlePrev();
      return;
    }
    handleNext();
  };

  const handleWheel = (event) => {
    if (!canSlide) return;
    if (Math.abs(event.deltaX) < 12 || Math.abs(event.deltaX) <= Math.abs(event.deltaY)) {
      return;
    }

    const now = Date.now();
    if (now - wheelLock.current < 450) return;
    wheelLock.current = now;

    event.preventDefault();
    if (event.deltaX > 0) {
      handleNext();
      return;
    }
    handlePrev();
  };

  if (!slides.length) return null;

  return (
    <section
      className={`qfx-hero ${isDragging ? "qfx-hero-dragging" : ""}`}
      ref={heroRef}
      onPointerDown={startDrag}
      onPointerMove={moveDrag}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onPointerLeave={endDrag}
      onWheel={handleWheel}
    >
      <div
        className="qfx-hero-track"
        ref={trackRef}
        style={slideTrackStyle}
        onTransitionEnd={handleTrackTransitionEnd}
      >
        {loopSlides.map((slide, index) => {
          const collab = slide.collab_details || null;
          const isCollab = slide.slide_type === "COLLAB";
          const isPromo = slide.slide_type === "PROMO";
          const badge = isPromo
            ? ""
            : slide.badge_text || (isCollab ? "Collaboration" : "Now Showing");
          const ctaLabel = isPromo
            ? ""
            : slide.cta_text || (isCollab ? "Learn More" : "Buy Ticket");
          const metaParts = [slide.genre, slide.year, slide.duration].filter(Boolean);
          const slideStyle = {
            "--qfx-bg": slide.image ? `url(${slide.image})` : "none",
            "--qfx-accent": collab?.primary_color || "#ff2e55",
            "--qfx-accent-2": collab?.secondary_color || "#ffb347",
          };

          return (
            <article
              key={`qfx-slide-${slide.id || "s"}-${index}`}
              className={`qfx-slide ${isCollab ? "qfx-slide-collab" : ""} ${isPromo ? "qfx-slide-promo" : ""}`}
              style={slideStyle}
            >
              <div className="qfx-slide-bg" />
              {!isPromo ? <div className="qfx-slide-overlay" /> : null}
              {!isPromo ? (
                <div className="qfx-slide-content">
                <div className="qfx-slide-left">
                  <span className="qfx-badge">{badge}</span>
                  {slide.subtitle ? <div className="qfx-subtitle">{slide.subtitle}</div> : null}
                  <h1 className="qfx-title">{slide.title || collab?.headline}</h1>

                  {isCollab ? (
                    <>
                      {collab?.offer_text ? (
                        <p className="qfx-offer">{collab.offer_text}</p>
                      ) : null}
                      {collab?.promo_code ? (
                        <div className="qfx-promo">
                          <span>{collab.promo_code_label || "Use Promocode"}</span>
                          <strong>{collab.promo_code}</strong>
                        </div>
                      ) : null}
                      {collab?.terms_text ? (
                        <div className="qfx-terms">{collab.terms_text}</div>
                      ) : null}
                    </>
                  ) : (
                    <>
                      {metaParts.length ? (
                        <div className="qfx-meta">
                          {metaParts.map((part, idx) => (
                            <span key={idx}>{part}</span>
                          ))}
                        </div>
                      ) : null}
                      {slide.description ? (
                        <p className="qfx-desc">{slide.description}</p>
                      ) : null}
                    </>
                  )}

                  {ctaLabel ? (
                    <button
                      type="button"
                      className="qfx-cta"
                      onClick={() => handleCta(slide)}
                    >
                      {ctaLabel}
                    </button>
                  ) : null}
                </div>

                {isCollab ? (
                  <div className="qfx-slide-right">
                    <div className="qfx-collab-card">
                      <div className="qfx-collab-logos">
                        {collab?.partner_logo ? (
                          <img src={collab.partner_logo} alt={collab.partner_name || "Partner"} />
                        ) : null}
                        {collab?.partner_logo_2 ? (
                          <>
                            <span className="qfx-collab-x">x</span>
                            <img src={collab.partner_logo_2} alt="Partner" />
                          </>
                        ) : null}
                      </div>
                      {collab?.headline ? (
                        <div className="qfx-collab-headline">{collab.headline}</div>
                      ) : null}
                      {collab?.right_badge_text ? (
                        <span className="qfx-collab-badge">{collab.right_badge_text}</span>
                      ) : null}
                    </div>
                  </div>
                ) : null}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>

      {slides.length > 1 ? (
        <>
          <button
            type="button"
            className="qfx-arrow qfx-arrow-left"
            onClick={handlePrev}
            aria-label="Previous slide"
          >
            <ChevronLeft size={20} />
          </button>
          <button
            type="button"
            className="qfx-arrow qfx-arrow-right"
            onClick={handleNext}
            aria-label="Next slide"
          >
            <ChevronRight size={20} />
          </button>
          <div className="qfx-dots">
            {slides.map((_, idx) => (
              <button
                key={`dot-${idx}`}
                type="button"
                className={`qfx-dot ${idx === activeRealIndex ? "active" : ""}`}
                onClick={() => moveToDot(idx)}
                aria-label={`Go to slide ${idx + 1}`}
              />
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
