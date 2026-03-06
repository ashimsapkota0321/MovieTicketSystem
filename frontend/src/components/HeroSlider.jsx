import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import api from "../api/api";
import "../css/hero-slider.css";

const AUTO_PLAY_MS = 5000;

export default function HeroSlider() {
  const navigate = useNavigate();
  const [slides, setSlides] = useState([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const autoRef = useRef(null);

  useEffect(() => {
    let mounted = true;
    const loadSlides = async () => {
      try {
        const response = await api.get("/api/home/now-showing-slides/");
        const nextSlides = response?.data?.slides || [];
        if (!mounted) return;
        setSlides(nextSlides);
        setActiveIndex(0);
      } catch {
        if (!mounted) return;
        setSlides([]);
      }
    };
    loadSlides();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!slides.length || slides.length === 1 || paused) return;
    autoRef.current = window.setInterval(() => {
      setActiveIndex((prev) => (prev + 1) % slides.length);
    }, AUTO_PLAY_MS);
    return () => window.clearInterval(autoRef.current);
  }, [slides.length, paused]);

  const handlePrev = () => {
    if (!slides.length) return;
    setActiveIndex((prev) => (prev - 1 + slides.length) % slides.length);
  };

  const handleNext = () => {
    if (!slides.length) return;
    setActiveIndex((prev) => (prev + 1) % slides.length);
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

  const slideTrackStyle = useMemo(
    () => ({ transform: `translate3d(-${activeIndex * 100}%, 0, 0)` }),
    [activeIndex]
  );

  if (!slides.length) return null;

  return (
    <section
      className="qfx-hero"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="qfx-hero-track" style={slideTrackStyle}>
        {slides.map((slide, index) => {
          const collab = slide.collab_details || null;
          const isCollab = slide.slide_type === "COLLAB";
          const badge = slide.badge_text || (isCollab ? "Collaboration" : "Now Showing");
          const ctaLabel = slide.cta_text || (isCollab ? "Learn More" : "Buy Ticket");
          const metaParts = [slide.genre, slide.year, slide.duration].filter(Boolean);
          const slideStyle = {
            "--qfx-bg": slide.image ? `url(${slide.image})` : "none",
            "--qfx-accent": collab?.primary_color || "#ff2e55",
            "--qfx-accent-2": collab?.secondary_color || "#ffb347",
          };

          return (
            <article
              key={slide.id || index}
              className={`qfx-slide ${isCollab ? "qfx-slide-collab" : ""}`}
              style={slideStyle}
            >
              <div className="qfx-slide-bg" />
              <div className="qfx-slide-overlay" />
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
                className={`qfx-dot ${idx === activeIndex ? "active" : ""}`}
                onClick={() => setActiveIndex(idx)}
                aria-label={`Go to slide ${idx + 1}`}
              />
            ))}
          </div>
        </>
      ) : null}
    </section>
  );
}
