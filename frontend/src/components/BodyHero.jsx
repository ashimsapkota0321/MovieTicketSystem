import React, { useEffect, useMemo, useState } from "react";
import { CalendarDays, Clock3, ChevronLeft, ChevronRight } from "lucide-react";

export default function BodyHero({
  slides = [],
  interval = 4000,
  badge = "Now Showing",
  variant = "default",
  cta,
}) {
  const normalized = useMemo(
    () =>
      (slides || []).map((s) =>
        typeof s === "string"
          ? { image: s }
          : {
              image: s.image || s.bg || s.poster || s.posterUrl || s.url,
              title: s.title || s.name,
              desc: s.desc || s.description,
              badge: s.badge,
              genre: s.genre,
              year: s.year,
              duration: s.duration,
            }
      ),
    [slides]
  );

  const [current, setCurrent] = useState(0);
  const canSlide = normalized.length > 1;

  useEffect(() => {
    if (normalized.length < 2) return;
    const id = setInterval(() => setCurrent((p) => (p + 1) % normalized.length), interval);
    return () => clearInterval(id);
  }, [normalized.length, interval]);

  const handlePrev = () => {
    if (!canSlide) return;
    setCurrent((prev) => (prev - 1 + normalized.length) % normalized.length);
  };

  const handleNext = () => {
    if (!canSlide) return;
    setCurrent((prev) => (prev + 1) % normalized.length);
  };

  const heroClass =
    variant === "full"
      ? "wf2-bodyHero wf2-bodyHeroFull"
      : "wf2-bodyHero";
  const trackStyle = { transform: `translateX(-${current * 100}%)` };

  return (
    <div className={heroClass}>
      <div className="wf2-bodyHeroTrack" style={trackStyle}>
        {normalized.map((item, idx) => {
          const slideStyle = item.image ? { "--hero-bg": `url(${item.image})` } : undefined;
          return (
            <div className="wf2-bodyHeroSlide" style={slideStyle} key={`hero-slide-${idx}`}>
              <div className="wf2-bodyHeroOverlay" />

              <div className="wf2-bodyHeroContent">
                <div className="wf2-heroBadge">{item.badge || badge}</div>
                {item.title ? (
                  <h2 className="wf2-bodyHeroTitle">
                    {item.title.split("\n").map((line, lineIdx) => (
                      <span key={lineIdx}>
                        {line}
                        <br />
                      </span>
                    ))}
                  </h2>
                ) : null}

                {item.genre || item.year || item.duration ? (
                  <div className="wf2-heroMeta wf2-bodyHeroMeta">
                    {item.genre ? (
                      <span className="wf2-metaItem">{item.genre}</span>
                    ) : null}
                    {item.year ? (
                      <span className="wf2-metaItem">
                        <CalendarDays size={16} />
                        {item.year}
                      </span>
                    ) : null}
                    {item.duration ? (
                      <span className="wf2-metaItem">
                        <Clock3 size={16} />
                        {item.duration}
                      </span>
                    ) : null}
                  </div>
                ) : null}

                {item.desc ? <p className="wf2-bodyHeroDesc">{item.desc}</p> : null}

                {cta ? (
                  <div className="wf2-heroBtns">
                    <button
                      className="wf2-btn wf2-btnPrimary wf2-btnPill wf2-btnWide"
                      type="button"
                      onClick={cta.onClick}
                    >
                      {cta.label}
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      {canSlide ? (
        <>
          <button
            className="wf2-heroArrow wf2-heroArrowLeft"
            type="button"
            onClick={handlePrev}
            aria-label="Previous slide"
          >
            <ChevronLeft size={20} />
          </button>
          <button
            className="wf2-heroArrow wf2-heroArrowRight"
            type="button"
            onClick={handleNext}
            aria-label="Next slide"
          >
            <ChevronRight size={20} />
          </button>
        </>
      ) : null}

      <div className="wf2-bodyHeroDots">
        {normalized.map((_, i) => (
          <button key={i} className={`dot ${i === current ? "active" : ""}`} onClick={() => setCurrent(i)} aria-label={`Slide ${i + 1}`} />
        ))}
      </div>
    </div>
  );
}
