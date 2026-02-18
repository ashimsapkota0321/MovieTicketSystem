import React, { useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, Clock3, ChevronLeft, ChevronRight } from "lucide-react";

export default function BodyHero({
  slides = [],
  interval = 4000,
  badge = "Now Showing",
  variant = "default",
  cta,
  onSlideClick,
}) {
  const normalized = useMemo(
    () =>
      (slides || []).map((s) =>
        typeof s === "string"
          ? { image: s }
          : {
              id: s.id || s._id || s.movieId,
              image: s.image || s.bg || s.poster || s.posterUrl || s.url,
              title: s.title || s.name,
              desc: s.desc || s.description,
              badge: s.badge,
              genre: s.genre,
              year: s.year,
              duration: s.duration,
              censor: s.censor || s.rating || s.certificate,
            }
      ),
    [slides]
  );

  const total = normalized.length;
  const canSlide = total > 1;
  const loopCopies = canSlide ? 7 : 1;
  const middleCopy = Math.floor(loopCopies / 2);
  const baseIndex = canSlide ? total * middleCopy : 0;
  const loopSlides = canSlide
    ? Array.from({ length: loopCopies * total }, (_, idx) => normalized[idx % total])
    : normalized;
  const [current, setCurrent] = useState(baseIndex);
  const [transitionEnabled, setTransitionEnabled] = useState(true);
  const heroRef = useRef(null);
  const currentRef = useRef(current);
  const dragState = useRef({
    active: false,
    startX: 0,
    lastX: 0,
    pointerId: null,
    startIndex: 0,
    moved: false,
  });
  const wheelLock = useRef(0);
  const [dragOffset, setDragOffset] = useState(0);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    currentRef.current = current;
  }, [current]);

  useEffect(() => {
    if (!canSlide || isDragging) return;
    const id = setInterval(() => setCurrent((p) => p + 1), interval);
    return () => clearInterval(id);
  }, [canSlide, interval, isDragging]);

  useEffect(() => {
    if (!canSlide) {
      setCurrent(0);
      return;
    }
    setTransitionEnabled(false);
    setCurrent(baseIndex);
    const id = requestAnimationFrame(() => setTransitionEnabled(true));
    return () => cancelAnimationFrame(id);
  }, [canSlide, baseIndex]);

  const handlePrev = () => {
    if (!canSlide) return;
    setCurrent((prev) => prev - 1);
  };

  const handleNext = () => {
    if (!canSlide) return;
    setCurrent((prev) => prev + 1);
  };

  const handleTransitionEnd = (event) => {
    if (event && event.target !== event.currentTarget) return;
    if (event && event.propertyName !== "transform") return;
    if (!canSlide) return;
    const minSafeIndex = total;
    const maxSafeIndex = total * (loopCopies - 1) - 1;
    if (current >= minSafeIndex && current <= maxSafeIndex) return;
    const normalizedIndex = ((current % total) + total) % total;
    const desired = baseIndex + normalizedIndex;
    if (desired === current) return;
    setTransitionEnabled(false);
    requestAnimationFrame(() => {
      currentRef.current = desired;
      setCurrent(desired);
      requestAnimationFrame(() => setTransitionEnabled(true));
    });
  };

  const clickable = typeof onSlideClick === "function";
  const heroClass = [
    variant === "full" ? "wf2-bodyHero wf2-bodyHeroFull" : "wf2-bodyHero",
    isDragging ? "wf2-bodyHeroDragging" : "",
    clickable ? "wf2-bodyHeroClickable" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const trackStyle = {
    transform: `translate3d(calc(-${current * 100}% + ${dragOffset}px), 0, 0)`,
    transition: isDragging || !transitionEnabled ? "none" : undefined,
  };

  const startDrag = (event) => {
    if (!canSlide) return;
    if (event.button !== undefined && event.button !== 0) return;
    const target = event.target;
    if (target && target.closest && target.closest("button, a, input, select, textarea")) {
      return;
    }
    dragState.current = {
      active: true,
      startX: event.clientX,
      lastX: event.clientX,
      pointerId: event.pointerId,
      startIndex: currentRef.current,
      moved: false,
    };
    setIsDragging(true);
    setDragOffset(0);
    if (event.currentTarget.setPointerCapture) {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
  };

  const moveDrag = (event) => {
    if (!dragState.current.active) return;
    const width = heroRef.current?.clientWidth || 1;
    const rawDelta = event.clientX - dragState.current.startX;
    if (!dragState.current.moved && Math.abs(rawDelta) > 6) {
      dragState.current.moved = true;
    }
    const slideDelta = Math.trunc(rawDelta / width);
    const nextCurrent = dragState.current.startIndex - slideDelta;
    const offset = rawDelta - slideDelta * width;

    dragState.current.lastX = event.clientX;
    if (nextCurrent !== currentRef.current) {
      currentRef.current = nextCurrent;
      setCurrent(nextCurrent);
    }
    setDragOffset(offset);
  };

  const endDrag = (event) => {
    if (!dragState.current.active) return;
    const endX =
      typeof event.clientX === "number" ? event.clientX : dragState.current.lastX;
    const width = heroRef.current?.clientWidth || 1;
    const rawDelta = endX - dragState.current.startX;
    const slideDelta = Math.trunc(rawDelta / width);
    const offset = rawDelta - slideDelta * width;
    const threshold = Math.min(140, width * 0.18);
    let moved = false;
    if (offset < -threshold) {
      moved = true;
      handleNext();
    } else if (offset > threshold) {
      moved = true;
      handlePrev();
    }
    dragState.current.active = false;
    setIsDragging(false);
    setDragOffset(0);
    if (!moved && canSlide) {
      const normalizedIndex = ((currentRef.current % total) + total) % total;
      const desired = baseIndex + normalizedIndex;
      if (desired !== currentRef.current) {
        setTransitionEnabled(false);
        setCurrent(desired);
        requestAnimationFrame(() => setTransitionEnabled(true));
      }
    }
    if (event.currentTarget.releasePointerCapture && dragState.current.pointerId !== null) {
      event.currentTarget.releasePointerCapture(dragState.current.pointerId);
    }
  };

  const handleSlideClick = (item, event) => {
    if (!clickable) return;
    if (dragState.current.moved) {
      dragState.current.moved = false;
      return;
    }
    const target = event.target;
    if (target && target.closest && target.closest("button, a, input, select, textarea")) {
      return;
    }
    onSlideClick(item);
  };

  const handleSlideKeyDown = (item, event) => {
    if (!clickable) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    onSlideClick(item);
  };

  const handleWheel = (event) => {
    if (!canSlide || isDragging || !transitionEnabled) return;
    if (Math.abs(event.deltaX) <= Math.abs(event.deltaY)) return;
    if (Math.abs(event.deltaX) < 18) return;
    const now = Date.now();
    if (now - wheelLock.current < 500) return;
    wheelLock.current = now;
    event.preventDefault();
    if (event.deltaX > 0) {
      handleNext();
    } else if (event.deltaX < 0) {
      handlePrev();
    }
  };

  const activeIndex = total ? ((current % total) + total) % total : 0;
  const moveToIndex = (targetIndex) => {
    if (!canSlide) {
      setCurrent(targetIndex);
      return;
    }
    const currentIndex = ((current % total) + total) % total;
    if (targetIndex === currentIndex) return;
    const forward = (targetIndex - currentIndex + total) % total;
    const backward = forward - total;
    const delta = Math.abs(backward) < forward ? backward : forward;
    setCurrent((prev) => prev + delta);
  };

  return (
    <div
      className={heroClass}
      ref={heroRef}
      onPointerDown={startDrag}
      onPointerMove={moveDrag}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onPointerLeave={endDrag}
      onWheel={handleWheel}
      aria-live="polite"
    >
      <div className="wf2-bodyHeroTrack" style={trackStyle} onTransitionEnd={handleTransitionEnd}>
        {loopSlides.map((item, idx) => {
          const slideStyle = item.image ? { "--hero-bg": `url(${item.image})` } : undefined;
          const slideClickable = clickable ? "wf2-bodyHeroSlideClickable" : "";
          const isActiveSlide = idx === current;
          return (
            <div
              className={`wf2-bodyHeroSlide ${slideClickable}`}
              style={slideStyle}
              key={`hero-slide-${idx}`}
              onClick={clickable ? (event) => handleSlideClick(item, event) : undefined}
              onKeyDown={clickable ? (event) => handleSlideKeyDown(item, event) : undefined}
              role={clickable ? "button" : undefined}
              tabIndex={clickable && isActiveSlide ? 0 : -1}
              aria-label={clickable && item.title ? `Open ${item.title}` : undefined}
            >
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
          <button
            key={i}
            className={`dot ${i === activeIndex ? "active" : ""}`}
            onClick={() => moveToIndex(i)}
            aria-label={`Slide ${i + 1}`}
          />
        ))}
      </div>
    </div>
  );
}
