import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { ChevronLeft, Play } from "lucide-react";
import "../css/seatSelection.css";

import { useAppContext } from "../context/Appcontext";
import {
  calculateBookingTicketPrice,
  fetchFoodItemsByVendor,
  releaseBookingSeats,
  reserveBookingSeats,
} from "../lib/catalogApi";
import { API_BASE } from "../lib/apiBase";
import gharjwai from "../images/gharjwai.jpg";
import avengers from "../images/avengers.jpg";
import degreemaila from "../images/degreemaila.jpg";
import balidan from "../images/balidan.jpg";

const defaultSeatGroups = [
  { key: "normal", label: "Normal", rows: ["A", "B", "C", "D"] },
  { key: "executive", label: "Executive", rows: ["E", "F", "G", "H"] },
  { key: "premium", label: "Premium", rows: ["I", "J"] },
  { key: "vip", label: "VIP", rows: ["K", "L"] },
];
const defaultSeatCols = Array.from({ length: 15 }, (_, i) => i + 1);
const MAX_SELECTION = 5;
const DEFAULT_SEAT_LOCK_HOLD_SECONDS = 10 * 60;
const SEAT_LOCK_WARNING_SECONDS = 60;

export default function SeatSelection() {
  const navigate = useNavigate();
  const location = useLocation();
  const ctx = safeUseAppContext();
  const shows = ctx?.movies ?? ctx?.shows ?? fallbackShows;
  const showtimes = ctx?.showtimes ?? [];
  const selection = location?.state || {};
  const selectedMovieState = selection.movie || null;
  const selectedVendorState = selection.vendor || null;
  const selectedShowState = selection.show || null;
  const selectedDateState =
    selection.date || selection.showDate || selection.show_date || selectedShowState?.date || selectedShowState?.show_date || "";
  const selectedTimeState =
    selection.time || selection.start || selection.start_time || selectedShowState?.start || selectedShowState?.start_time || "";
  const movie = useMemo(() => shows?.[0] ?? fallbackShows[0], [shows]);
  const displayMovie = useMemo(
    () => selectedMovieState || movie,
    [selectedMovieState, movie]
  );
  const [selectedDate, setSelectedDate] = useState(() =>
    normalizeDateValue(selectedDateState)
  );
  const [selectedTime, setSelectedTime] = useState(() =>
    formatTime(selectedTimeState)
  );
  const showtimeInfo = useMemo(
    () =>
      buildSeatShowtimes(
        showtimes,
        selectedMovieState || displayMovie,
        selectedVendorState,
        selectedDate,
        null
      ),
    [showtimes, selectedMovieState, displayMovie, selectedVendorState, selectedDate]
  );

  useEffect(() => {
    const nextDate = normalizeDateValue(showtimeInfo?.activeDate);
    if (!nextDate) return;
    setSelectedDate((prev) => {
      const current = normalizeDateValue(prev);
      if (
        current &&
        Array.isArray(showtimeInfo?.dates) &&
        showtimeInfo.dates.includes(current)
      ) {
        return prev;
      }
      return nextDate;
    });
  }, [showtimeInfo?.activeDate, showtimeInfo?.dates]);

  useEffect(() => {
    if (!Array.isArray(showtimeInfo?.times) || !showtimeInfo.times.length) {
      return;
    }
    setSelectedTime((prev) => {
      const current = formatTime(prev);
      if (current && showtimeInfo.times.includes(current)) {
        return prev;
      }
      return showtimeInfo.times[0];
    });
  }, [showtimeInfo?.times]);
  const initialSelectedSeats = useMemo(() => {
    if (!Array.isArray(selection?.selectedSeats)) return [];
    const normalized = selection.selectedSeats
      .map((seat) => normalizeSeatLabel(seat))
      .filter(Boolean);
    return Array.from(new Set(normalized));
  }, [selection?.selectedSeats]);

  const [selectedSeats, setSelectedSeats] = useState(() => initialSelectedSeats);
  const [toastMessage, setToastMessage] = useState("");
  const [toastOpen, setToastOpen] = useState(false);
  const [toastVisible, setToastVisible] = useState(false);
  const toastTimerRef = useRef(null);
  const toastHideRef = useRef(null);
  const [pricingPreview, setPricingPreview] = useState(null);
  const [pricingLoading, setPricingLoading] = useState(false);
  const [pricingError, setPricingError] = useState("");
  const [priceLock, setPriceLock] = useState(null);
  const [seatHoldSeconds, setSeatHoldSeconds] = useState(
    DEFAULT_SEAT_LOCK_HOLD_SECONDS
  );
  const [seatLockBySeat, setSeatLockBySeat] = useState({});
  const [seatLockSecondsLeft, setSeatLockSecondsLeft] = useState(0);
  const [seatLockTimedOut, setSeatLockTimedOut] = useState(false);
  const [queuedToastMessage, setQueuedToastMessage] = useState("");
  const [soldSeatSet, setSoldSeatSet] = useState(() => new Set());
  const [unavailableSeatSet, setUnavailableSeatSet] = useState(() => new Set());
  const [reservedSeatSet, setReservedSeatSet] = useState(() => new Set());
  const [pendingSeatSet, setPendingSeatSet] = useState(() => new Set());
  const [dynamicSeatGroups, setDynamicSeatGroups] = useState(defaultSeatGroups);
  const [dynamicSeatCols, setDynamicSeatCols] = useState(defaultSeatCols);
  const [proceeding, setProceeding] = useState(false);
  const selectedSeatsRef = useRef([]);
  const skipReleaseOnUnmountRef = useRef(false);
  const pendingSeatSetRef = useRef(new Set());
  const seatLockBySeatRef = useRef({});
  const seatLockExpiryHandledRef = useRef(false);

  const title = displayMovie?.title || displayMovie?.name || "Hami Teen Bhai";
  const poster =
    displayMovie?.poster ||
    displayMovie?.posterUrl ||
    displayMovie?.image ||
    gharjwai;
  const seatSubtitle = "2h 10m | Action, Comedy | May 2018 | UA 13+";
  const totalSeats = selectedSeats.length;
  const totalPrice = Number(pricingPreview?.total || pricingPreview?.subtotal || 0);
  const dynamicBaseSubtotal = Number(pricingPreview?.breakdown?.base_subtotal || 0);
  const dynamicRuleAdjustment = Number(pricingPreview?.breakdown?.rule_adjustment || 0);
  const dynamicOccupancyAdjustment = Number(pricingPreview?.breakdown?.occupancy_adjustment || 0);
  const dynamicByCategory =
    pricingPreview && typeof pricingPreview.dynamic_by_category === "object"
      ? pricingPreview.dynamic_by_category
      : {};
  const selectedShow = useMemo(
    () =>
      selectedShowState ||
      findMatchingShow(
        showtimes,
        selectedMovieState || displayMovie,
        selectedVendorState,
        selectedDate,
        selectedTime
      ),
    [
      selectedShowState,
      showtimes,
      selectedMovieState,
      displayMovie,
      selectedVendorState,
      selectedDate,
      selectedTime,
    ]
  );
  const bookingMovieId = useMemo(
    () =>
      coerceInt(
        selectedMovieState?.id ||
          selectedMovieState?._id ||
          displayMovie?.id ||
          displayMovie?._id ||
          selectedShow?.movieId ||
          selectedShow?.movie_id
      ),
    [selectedMovieState, displayMovie, selectedShow]
  );
  const bookingCinemaId = useMemo(
    () =>
      coerceInt(
        selectedVendorState?.id ||
          selectedVendorState?.vendorId ||
          selectedVendorState?.vendor_id ||
          selectedShow?.vendorId ||
          selectedShow?.vendor_id
      ),
    [selectedVendorState, selectedShow]
  );
  const bookingShowId = useMemo(
    () => coerceInt(selection.showId || selection.show_id || selectedShow?.id),
    [selection.showId, selection.show_id, selectedShow]
  );
  const bookingHall = String(
    selection.hall || selection.cinemaHall || selectedShow?.hall || ""
  ).trim();
  const bookingDateValue = useMemo(
    () =>
      normalizeDateValue(
        selectedDate || selectedShow?.date || selectedShow?.show_date
      ),
    [selectedDate, selectedShow]
  );
  const bookingTimeValue = useMemo(
    () =>
      toApiTime(
        selectedTime ||
          selectedShow?.start ||
          selectedShow?.start_time ||
          selectedShow?.startTime
      ),
    [selectedTime, selectedShow]
  );
  const selectedSeatLabels = useMemo(
    () => [...selectedSeats].sort((a, b) => seatSortKey(a) - seatSortKey(b)),
    [selectedSeats]
  );
  const activeSeatLockDeadline = useMemo(() => {
    if (!selectedSeatLabels.length) return null;
    const lockDeadlines = selectedSeatLabels
      .map((seat) => seatLockBySeat[normalizeSeatLabel(seat)])
      .filter((value) => Number.isFinite(value));
    if (!lockDeadlines.length) return null;
    return Math.min(...lockDeadlines);
  }, [selectedSeatLabels, seatLockBySeat]);
  const seatLockInWarning =
    seatLockSecondsLeft > 0 && seatLockSecondsLeft <= SEAT_LOCK_WARNING_SECONDS;
  const seatLockTimerLabel = activeSeatLockDeadline
    ? formatCountdown(seatLockSecondsLeft)
    : "Syncing...";

  const refreshDynamicPricing = useCallback(async () => {
    if (
      !bookingMovieId ||
      !bookingCinemaId ||
      !bookingDateValue ||
      !bookingTimeValue ||
      !selectedSeatLabels.length
    ) {
      setPricingPreview(null);
      setPricingError("");
      setPriceLock(null);
      return;
    }

    setPricingLoading(true);
    setPricingError("");
    try {
      const payload = buildBookingPayload(
        bookingMovieId,
        bookingCinemaId,
        bookingDateValue,
        bookingTimeValue,
        bookingShowId,
        bookingHall,
        selectedSeatLabels
      );
      payload.lock_price = true;

      const response = await calculateBookingTicketPrice(payload);
      setPricingPreview(response || null);
      setPriceLock(response?.price_lock || null);
    } catch (error) {
      setPricingPreview(null);
      setPriceLock(null);
      setPricingError(error?.message || "Unable to calculate dynamic ticket price.");
    } finally {
      setPricingLoading(false);
    }
  }, [
    bookingMovieId,
    bookingCinemaId,
    bookingDateValue,
    bookingTimeValue,
    bookingShowId,
    bookingHall,
    selectedSeatLabels,
  ]);

  useEffect(() => {
    refreshDynamicPricing();
  }, [refreshDynamicPricing]);

  const applySeatPayload = useCallback((data) => {
    const groups = Array.isArray(data?.seat_groups) && data.seat_groups.length
      ? data.seat_groups
      : defaultSeatGroups;
    const uniqueGroups = ensureUniqueGroupRows(groups);
    const columns = Array.isArray(data?.seat_columns) && data.seat_columns.length
      ? data.seat_columns
          .map((value) => Number(value))
          .filter((value) => Number.isInteger(value) && value > 0)
      : defaultSeatCols;
    const soldSeats = Array.isArray(data?.sold_seats)
      ? data.sold_seats
      : Array.isArray(data?.soldSeats)
        ? data.soldSeats
        : [];
    const unavailableSeats = Array.isArray(data?.unavailable_seats)
      ? data.unavailable_seats
      : Array.isArray(data?.unavailableSeats)
        ? data.unavailableSeats
        : [];
    const reservedSeats = Array.isArray(data?.reserved_seats)
      ? data.reserved_seats
      : Array.isArray(data?.reservedSeats)
        ? data.reservedSeats
        : [];

    const nextSoldSet = new Set(
      soldSeats.map((seat) => normalizeSeatLabel(seat)).filter(Boolean)
    );
    const nextUnavailableSet = new Set(
      unavailableSeats.map((seat) => normalizeSeatLabel(seat)).filter(Boolean)
    );
    const nextReservedSet = new Set(
      reservedSeats.map((seat) => normalizeSeatLabel(seat)).filter(Boolean)
    );
    const nextReservedSeatLocks = parseSeatLockDeadlines(data?.reserved_seat_locks);
    const holdMinutes = Number(data?.reservation_hold_minutes);

    if (Number.isFinite(holdMinutes) && holdMinutes > 0) {
      setSeatHoldSeconds(Math.max(30, Math.round(holdMinutes * 60)));
    }

    const currentSelected = Array.isArray(selectedSeatsRef.current)
      ? selectedSeatsRef.current
      : [];
    const currentSelectedLabels = currentSelected
      .map((seat) => normalizeSeatLabel(seat))
      .filter(Boolean);
    const pendingLabels = new Set(
      Array.from(pendingSeatSetRef.current || [])
        .map((seat) => normalizeSeatLabel(seat))
        .filter(Boolean)
    );

    const timedOutLabels = [];
    for (const label of currentSelectedLabels) {
      if (nextSoldSet.has(label) || nextUnavailableSet.has(label)) {
        continue;
      }
      if (nextReservedSet.has(label)) {
        continue;
      }
      if (pendingLabels.has(label)) {
        continue;
      }
      timedOutLabels.push(label);
    }

    if (timedOutLabels.length) {
      const seatText = formatSeatLabelList(timedOutLabels);
      setSeatLockTimedOut(true);
      setPriceLock(null);
      setQueuedToastMessage(
        `Seat hold expired for ${seatText}. Please reselect to continue.`
      );
    }

    setDynamicSeatGroups(uniqueGroups);
    setDynamicSeatCols(columns.length ? columns : defaultSeatCols);
    setSoldSeatSet(nextSoldSet);
    setUnavailableSeatSet(nextUnavailableSet);
    setReservedSeatSet(nextReservedSet);
    setSeatLockBySeat((prev) => {
      const nowMs = Date.now();
      const next = {};
      const selectedLabelSet = new Set(currentSelectedLabels);
      for (const label of selectedLabelSet) {
        const fromServer = nextReservedSeatLocks[label];
        const existing = prev[label];
        const candidate = Number.isFinite(fromServer)
          ? fromServer
          : Number.isFinite(existing)
            ? existing
            : null;
        if (Number.isFinite(candidate) && candidate > nowMs) {
          next[label] = candidate;
        }
      }
      return next;
    });
    setSelectedSeats((prev) =>
      prev.filter((seat) => {
        const label = normalizeSeatLabel(seat);
        if (nextSoldSet.has(label) || nextUnavailableSet.has(label)) {
          return false;
        }
        return nextReservedSet.has(label);
      })
    );
  }, []);

  const releaseExpiredSeatLocks = useCallback(
    async (expiredSeats) => {
      const normalizedSeats = Array.from(
        new Set(
          (Array.isArray(expiredSeats) ? expiredSeats : [])
            .map((seat) => normalizeSeatLabel(seat))
            .filter(Boolean)
        )
      ).sort((a, b) => seatSortKey(a) - seatSortKey(b));
      if (!normalizedSeats.length) return;

      const expiredSet = new Set(normalizedSeats);
      setSelectedSeats((prev) =>
        prev.filter((seat) => !expiredSet.has(normalizeSeatLabel(seat)))
      );
      setSeatLockBySeat((prev) => {
        const next = { ...prev };
        for (const seat of normalizedSeats) {
          delete next[seat];
        }
        return next;
      });
      setSeatLockTimedOut(true);
      setPriceLock(null);
      setQueuedToastMessage(
        `Seat hold expired for ${formatSeatLabelList(normalizedSeats)}. Please reselect to continue.`
      );

      if (!bookingMovieId || !bookingCinemaId || !bookingDateValue || !bookingTimeValue) {
        return;
      }

      try {
        const payload = buildBookingPayload(
          bookingMovieId,
          bookingCinemaId,
          bookingDateValue,
          bookingTimeValue,
          bookingShowId,
          bookingHall,
          normalizedSeats
        );
        const data = await releaseBookingSeats(payload);
        applySeatPayload(data);
      } catch {
        // Seat lock already expired server-side; no further action is required.
      }
    },
    [
      applySeatPayload,
      bookingMovieId,
      bookingCinemaId,
      bookingDateValue,
      bookingTimeValue,
      bookingShowId,
      bookingHall,
    ]
  );

  const dismissToast = () => {
    setToastOpen(false);
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
      toastTimerRef.current = null;
    }
    if (toastHideRef.current) {
      clearTimeout(toastHideRef.current);
    }
    toastHideRef.current = setTimeout(() => {
      setToastVisible(false);
    }, 240);
  };

  const showToast = (message) => {
    setToastMessage(message);
    setToastVisible(true);
    if (toastHideRef.current) {
      clearTimeout(toastHideRef.current);
      toastHideRef.current = null;
    }
    requestAnimationFrame(() => setToastOpen(true));
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
    }
    toastTimerRef.current = setTimeout(() => {
      dismissToast();
    }, 3000);
  };

  useEffect(() => {
    if (!queuedToastMessage) return;
    showToast(queuedToastMessage);
    setQueuedToastMessage("");
  }, [queuedToastMessage, showToast]);

  useEffect(() => () => {
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
    }
    if (toastHideRef.current) {
      clearTimeout(toastHideRef.current);
    }
  }, []);

  useEffect(() => {
    if (!toastVisible) return;

    const handleScroll = () => {
      dismissToast();
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [toastVisible]);

  const fetchSeatLayout = useCallback(async () => {
    if (!bookingMovieId || !bookingCinemaId || !bookingDateValue || !bookingTimeValue) {
      setSoldSeatSet(new Set());
      setUnavailableSeatSet(new Set());
      setReservedSeatSet(new Set());
      setSeatLockBySeat({});
      setSeatLockSecondsLeft(0);
      setSeatLockTimedOut(false);
      setDynamicSeatGroups(defaultSeatGroups);
      setDynamicSeatCols(defaultSeatCols);
      return;
    }

    const params = new URLSearchParams();
    params.set("movie_id", String(bookingMovieId));
    params.set("cinema_id", String(bookingCinemaId));
    params.set("date", bookingDateValue);
    params.set("time", bookingTimeValue);
    if (bookingShowId) params.set("show_id", String(bookingShowId));
    if (bookingHall) params.set("hall", bookingHall);

    const response = await fetch(
      `${API_BASE}/api/booking/seat-layout/?${params.toString()}`,
      {
        headers: {
          Accept: "application/json",
        },
      }
    );
    if (!response.ok) {
      throw new Error("Failed to load seat layout");
    }
    const data = await response.json();

    applySeatPayload(data);
  }, [
    bookingMovieId,
    bookingCinemaId,
    bookingDateValue,
    bookingTimeValue,
    bookingShowId,
    bookingHall,
    applySeatPayload,
  ]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        await fetchSeatLayout();
      } catch {
        if (!active) return;
        setSoldSeatSet(new Set());
        setUnavailableSeatSet(new Set());
        setReservedSeatSet(new Set());
        setSeatLockBySeat({});
        setSeatLockSecondsLeft(0);
        setDynamicSeatGroups(defaultSeatGroups);
        setDynamicSeatCols(defaultSeatCols);
      }
    };

    load();
    return () => {
      active = false;
    };
  }, [fetchSeatLayout]);

  useEffect(() => {
    selectedSeatsRef.current = selectedSeats;
  }, [selectedSeats]);

  useEffect(() => {
    pendingSeatSetRef.current = pendingSeatSet;
  }, [pendingSeatSet]);

  useEffect(() => {
    seatLockBySeatRef.current = seatLockBySeat;
  }, [seatLockBySeat]);

  useEffect(() => {
    if (!selectedSeatLabels.length) {
      setSeatLockBySeat({});
      setSeatLockSecondsLeft(0);
      return;
    }

    const nowMs = Date.now();
    const fallbackDeadline = nowMs + (seatHoldSeconds * 1000);
    setSeatLockBySeat((prev) => {
      const selectedLabelSet = new Set(
        selectedSeatLabels.map((seat) => normalizeSeatLabel(seat))
      );
      const next = {};
      let changed = false;

      for (const seatLabel of selectedLabelSet) {
        const existing = prev[seatLabel];
        if (Number.isFinite(existing) && existing > nowMs) {
          next[seatLabel] = existing;
          continue;
        }
        next[seatLabel] = fallbackDeadline;
        changed = true;
      }

      if (Object.keys(prev).length !== Object.keys(next).length) {
        changed = true;
      }

      return changed ? next : prev;
    });
  }, [selectedSeatLabels, seatHoldSeconds]);

  useEffect(() => {
    if (!activeSeatLockDeadline || !selectedSeatLabels.length) {
      seatLockExpiryHandledRef.current = false;
      setSeatLockSecondsLeft(0);
      return;
    }

    const tick = () => {
      const remainingSeconds = Math.max(
        0,
        Math.ceil((activeSeatLockDeadline - Date.now()) / 1000)
      );
      setSeatLockSecondsLeft(remainingSeconds);

      if (remainingSeconds > 0) {
        seatLockExpiryHandledRef.current = false;
        return;
      }
      if (seatLockExpiryHandledRef.current) {
        return;
      }
      seatLockExpiryHandledRef.current = true;

      const nowMs = Date.now();
      const expiredSeats = (selectedSeatsRef.current || []).filter((seat) => {
        const deadline = seatLockBySeatRef.current[normalizeSeatLabel(seat)];
        return Number.isFinite(deadline) && deadline <= nowMs;
      });
      if (expiredSeats.length) {
        releaseExpiredSeatLocks(expiredSeats);
      }
    };

    tick();
    const intervalId = setInterval(tick, 1000);
    return () => clearInterval(intervalId);
  }, [activeSeatLockDeadline, selectedSeatLabels.length, releaseExpiredSeatLocks]);

  useEffect(() => {
    if (!bookingMovieId || !bookingCinemaId || !bookingDateValue || !bookingTimeValue) {
      return;
    }
    const intervalId = setInterval(() => {
      fetchSeatLayout().catch(() => {});
    }, 8000);
    return () => clearInterval(intervalId);
  }, [fetchSeatLayout, bookingMovieId, bookingCinemaId, bookingDateValue, bookingTimeValue]);

  useEffect(() => {
    return () => {
      if (skipReleaseOnUnmountRef.current) {
        return;
      }
      if (
        !bookingMovieId ||
        !bookingCinemaId ||
        !bookingDateValue ||
        !bookingTimeValue
      ) {
        return;
      }
      const seatsToRelease = selectedSeatsRef.current || [];
      if (!seatsToRelease.length) return;
      const payload = buildBookingPayload(
        bookingMovieId,
        bookingCinemaId,
        bookingDateValue,
        bookingTimeValue,
        bookingShowId,
        bookingHall,
        seatsToRelease
      );
      releaseBookingSeats({
        ...payload,
        track_dropoff: true,
        dropoff_stage: "BOOKING",
        dropoff_reason: "LEFT_BOOKING_PROCESS",
      }).catch(() => {});
    };
  }, [
    bookingMovieId,
    bookingCinemaId,
    bookingDateValue,
    bookingTimeValue,
    bookingShowId,
    bookingHall,
  ]);

  const toggleSeat = async (key) => {
    const normalizedSeat = normalizeSeatLabel(key);
    if (selectedSeats.includes(key)) {
      if (!bookingMovieId || !bookingCinemaId || !bookingDateValue || !bookingTimeValue) {
        setSelectedSeats(selectedSeats.filter((seat) => seat !== key));
        setSeatLockTimedOut(false);
        return;
      }
      setPendingSeatSet((prev) => {
        const next = new Set(prev);
        next.add(key);
        return next;
      });
      try {
        const payload = buildBookingPayload(
          bookingMovieId,
          bookingCinemaId,
          bookingDateValue,
          bookingTimeValue,
          bookingShowId,
          bookingHall,
          [key]
        );
        const data = await releaseBookingSeats(payload);
        applySeatPayload(data);
        setSelectedSeats((prev) => prev.filter((seat) => seat !== key));
        setSeatLockBySeat((prev) => {
          const next = { ...prev };
          delete next[normalizedSeat];
          return next;
        });
        setSeatLockTimedOut(false);
      } catch (error) {
        showToast(error.message || "Failed to release seat.");
      } finally {
        setPendingSeatSet((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
      return;
    }

    if (
      reservedSeatSet.has(normalizedSeat) ||
      soldSeatSet.has(normalizedSeat) ||
      unavailableSeatSet.has(normalizedSeat)
    ) {
      return;
    }

    if (selectedSeats.length >= MAX_SELECTION) {
      showToast(`You can book upto ${MAX_SELECTION} seats`);
      return;
    }

    if (!bookingMovieId || !bookingCinemaId || !bookingDateValue || !bookingTimeValue) {
      setSelectedSeats([...selectedSeats, key]);
      setSeatLockTimedOut(false);
      return;
    }

    setPendingSeatSet((prev) => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
    try {
      const payload = buildBookingPayload(
        bookingMovieId,
        bookingCinemaId,
        bookingDateValue,
        bookingTimeValue,
        bookingShowId,
        bookingHall,
        [key]
      );
      const data = await reserveBookingSeats(payload);
      applySeatPayload(data);
      const conflicts = data?.conflicts || {};
      if (
        (conflicts.sold && conflicts.sold.length) ||
        (conflicts.unavailable && conflicts.unavailable.length) ||
        (conflicts.reserved && conflicts.reserved.length) ||
        (conflicts.invalid && conflicts.invalid.length)
      ) {
        if (conflicts.reserved && conflicts.reserved.length) {
          showToast("Seat is currently locked. Please pick another seat.");
        } else if (conflicts.sold && conflicts.sold.length) {
          showToast("Seat was sold while you were selecting. Please choose another.");
        } else if (conflicts.unavailable && conflicts.unavailable.length) {
          showToast("Seat is marked unavailable for this show.");
        } else {
          showToast("Seat selection is invalid. Please reselect.");
        }
        return;
      }
      const lockMapFromResponse = parseSeatLockDeadlines(data?.reserved_seat_locks);
      const fallbackLockDeadline = Date.now() + (seatHoldSeconds * 1000);
      const lockDeadline = Number.isFinite(lockMapFromResponse[normalizedSeat])
        ? lockMapFromResponse[normalizedSeat]
        : fallbackLockDeadline;
      setSeatLockBySeat((prev) => ({
        ...prev,
        [normalizedSeat]: lockDeadline,
      }));
      setSeatLockTimedOut(false);
      setSelectedSeats((prev) => [...prev, key]);
    } catch (error) {
      showToast(error.message || "Failed to reserve seat.");
    } finally {
      setPendingSeatSet((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  };

  const renderSelectedSeats = () => {
    if (selectedSeats.length) {
      return selectedSeats.map((seat) => (
        <span className="seat-pill" key={seat}>
          {seat}
        </span>
      ));
    }

    return <span className="seat-empty">Tap seats to add up to {MAX_SELECTION}.</span>;
  };

  const handleDateChange = (dateValue) => {
    const nextDate = normalizeDateValue(dateValue);
    if (!nextDate || nextDate === bookingDateValue) return;

    if (
      selectedSeats.length &&
      bookingMovieId &&
      bookingCinemaId &&
      bookingDateValue &&
      bookingTimeValue
    ) {
      const payload = buildBookingPayload(
        bookingMovieId,
        bookingCinemaId,
        bookingDateValue,
        bookingTimeValue,
        bookingShowId,
        bookingHall,
        selectedSeats
      );
      releaseBookingSeats(payload).catch(() => {});
    }

    const nextInfo = buildSeatShowtimes(
      showtimes,
      selectedMovieState || displayMovie,
      selectedVendorState,
      nextDate,
      null
    );
    const nextTime =
      Array.isArray(nextInfo?.times) && nextInfo.times.length ? nextInfo.times[0] : "";

    setSelectedDate(nextDate);
    setSelectedTime(nextTime);
    setSelectedSeats([]);
    setSeatLockBySeat({});
    setSeatLockSecondsLeft(0);
    setSeatLockTimedOut(false);
    setPriceLock(null);
  };

  const handleTimeChange = (time) => {
    if (!time || time === selectedTime) return;
    if (
      selectedSeats.length &&
      bookingMovieId &&
      bookingCinemaId &&
      bookingDateValue &&
      bookingTimeValue
    ) {
      const payload = buildBookingPayload(
        bookingMovieId,
        bookingCinemaId,
        bookingDateValue,
        bookingTimeValue,
        bookingShowId,
        bookingHall,
        selectedSeats
      );
      releaseBookingSeats(payload).catch(() => {});
    }
    setSelectedTime(time);
    setSelectedSeats([]);
    setSeatLockBySeat({});
    setSeatLockSecondsLeft(0);
    setSeatLockTimedOut(false);
    setPriceLock(null);
  };

  const handleCancelSelection = async () => {
    const seatsToRelease = [...selectedSeats];
    setSelectedSeats([]);
    setSeatLockBySeat({});
    setSeatLockSecondsLeft(0);
    setSeatLockTimedOut(false);
    setPriceLock(null);

    if (!seatsToRelease.length) {
      return;
    }
    if (!bookingMovieId || !bookingCinemaId || !bookingDateValue || !bookingTimeValue) {
      return;
    }

    try {
      const payload = buildBookingPayload(
        bookingMovieId,
        bookingCinemaId,
        bookingDateValue,
        bookingTimeValue,
        bookingShowId,
        bookingHall,
        seatsToRelease
      );
      const data = await releaseBookingSeats(payload);
      applySeatPayload(data);
    } catch {
      // Ignore release errors during user-initiated reset.
    }
  };

  const handleProceed = async () => {
    if (!selectedSeatLabels.length) {
      showToast("Select seats first.");
      return;
    }
    if (!bookingMovieId || !bookingCinemaId || !bookingDateValue || !bookingTimeValue) {
      showToast("Select a valid show before continuing.");
      return;
    }
    if (activeSeatLockDeadline && activeSeatLockDeadline <= Date.now()) {
      showToast("Seat hold has expired. Please reselect your seats.");
      return;
    }
    if (pricingLoading) {
      showToast("Pricing is updating. Please wait a moment.");
      return;
    }
    if (pricingError) {
      showToast(pricingError);
      return;
    }
    if (!pricingPreview) {
      showToast("Unable to fetch dynamic pricing. Please reselect your seats.");
      return;
    }

    const venueName =
      showtimeInfo.venueLabel || resolveVendorLabel(selectedVendorState) || "QFX Cinemas";
    const venueDate = bookingDateValue
      ? formatVenueDate(bookingDateValue)
      : formatVenueDate(selectedDate);
    const venueTime = selectedTime || formatTime(bookingTimeValue);
    const cinemaLocation = [
      selectedShow?.theatre || selectedVendorState?.theatre || "",
      selectedShow?.city || selectedVendorState?.city || "",
    ]
      .filter(Boolean)
      .join(", ");
    const venueText = [venueName, venueDate, venueTime].filter(Boolean).join(", ");
    const seatText = `Seat No: ${selectedSeatLabels.join(", ")}`;
    const currentUser = getStoredUser();

    const nextState = {
      movie: {
        title,
        language: displayMovie?.language || "Nepali",
        runtime: displayMovie?.duration || "2h 10m",
        seat: seatText,
        venue: venueText,
        cinemaName: venueName,
        cinemaLocation: cinemaLocation || "Location not provided",
        showDate: bookingDateValue,
        showTime: venueTime,
        hall: bookingHall,
        theater: bookingHall,
        poster,
        movieId: bookingMovieId,
        cinemaId: bookingCinemaId,
      },
      ticketTotal: totalPrice,
      selectedSeats: selectedSeatLabels,
      bookingContext: {
        showId: bookingShowId,
        movieId: bookingMovieId,
        cinemaId: bookingCinemaId,
        hall: bookingHall,
        date: bookingDateValue,
        time: bookingTimeValue,
        selectedSeats: selectedSeatLabels,
        priceLockToken: priceLock?.token || null,
        priceLockExpiresAt: priceLock?.expires_at || null,
        userId: currentUser?.id || null,
      },
      pricing: {
        ...(pricingPreview || {}),
        price_lock_token: priceLock?.token || null,
        price_lock_expires_at: priceLock?.expires_at || null,
      },
    };

    setProceeding(true);
    try {
      const vendorItems = await fetchFoodItemsByVendor({
        vendorId: bookingCinemaId,
        hall: bookingHall || "",
      });
      const hasFood = Array.isArray(vendorItems) && vendorItems.length > 0;
      skipReleaseOnUnmountRef.current = true;
      navigate(hasFood ? "/food" : "/order-confirm", { state: nextState });
    } catch {
      skipReleaseOnUnmountRef.current = true;
      navigate("/order-confirm", { state: nextState });
    } finally {
      setProceeding(false);
    }
  };

  const toastMarkup =
    toastVisible && typeof document !== "undefined"
      ? createPortal(
          <div
            className={`seat-toast ${toastOpen ? "seat-toast--show" : ""}`}
            role="status"
            aria-live="polite"
          >
            <span className="seat-toastText">{toastMessage}</span>
            <button
              className="seat-toastClose"
              type="button"
              onClick={dismissToast}
              aria-label="Dismiss"
            >
              x
            </button>
          </div>,
          document.body
        )
      : null;

  return (
    <div className="seat-page">
      {toastMarkup}
      <div className="seat-wrap">
        <div className="seat-header">
          <button
            className="seat-backBtn"
            type="button"
            onClick={() => navigate(-1)}
            aria-label="Go back"
          >
            <ChevronLeft size={18} />
          </button>
          <div>
            <h2 className="seat-title">{title}</h2>
            <p className="seat-subtitle">{seatSubtitle}</p>
          </div>
        </div>

        <div className="seat-top">
          <div className="seat-card">
            <div className="seat-poster">
              <img src={poster} alt={title} />
              <button className="seat-playBtn" type="button" aria-label="Play trailer">
                <Play size={18} />
              </button>
            </div>
          </div>

            <div className="seat-card">
            <div className="seat-cardTitle">
              {showtimeInfo.venueLabel || "QFX Cinemas"}
            </div>
            <div className="seat-cardSub">
              {showtimeInfo.subtitle || "Shows Today, Seat Challenge"}
            </div>
            {Array.isArray(showtimeInfo.dates) && showtimeInfo.dates.length ? (
              <div className="seat-showdates" aria-label="Show dates">
                {showtimeInfo.dates.map((dateValue) => (
                  <button
                    key={dateValue}
                    type="button"
                    className={`seat-dateChip${bookingDateValue === dateValue ? " seat-dateChipActive" : ""}`}
                    onClick={() => handleDateChange(dateValue)}
                    aria-pressed={bookingDateValue === dateValue}
                  >
                    {formatChipDate(dateValue)}
                  </button>
                ))}
              </div>
            ) : null}
            <div className="seat-showtimes">
              {(showtimeInfo.times.length
                ? showtimeInfo.times
                : ["10:00 AM", "12:30 PM", "2:00 PM", "6:30 PM", "9:00 PM", "10:30 PM"]
              ).map((time) => (
                <button
                  className={`seat-timeChip${selectedTime === time ? " seat-timeChipActive" : ""}`}
                  type="button"
                  key={time}
                  onClick={() => handleTimeChange(time)}
                  aria-pressed={selectedTime === time}
                >
                  {time}
                </button>
              ))}
            </div>
          </div>

          <div className="seat-card">
            <div className="seat-cardTitle">Movie Details</div>
            <div className="seat-detailsList">
              <div>Language: <span>Nepali</span></div>
              <div>Genre: <span>Action, Comedy</span></div>
              <div>Censor: <span>UA 13+</span></div>
              <div>Starring: <span>Rajesh Hamal, Nikhil Upreti, Shree Krishna</span></div>
              <div>Director: <span>Shive Regrin</span></div>
            </div>
          </div>
        </div>

        <div className="seat-layout">
          <div>
            <div className="seat-mapHeader">
              <div className="seat-mapLabel">Select Your Seat</div>
              <div className="seat-screen">
                <span>SCREEN</span>
                <div className="seat-curve" />
              </div>
            </div>

            <div className="seat-mapCard">
              <div className="seat-map" style={{ "--seat-count": dynamicSeatCols.length }}>
                {dynamicSeatGroups.map((group) => (
                  <div className={`seat-group seat-group--${group.key}`} key={group.label}>
                    <div className="seat-groupTitle">{group.label}</div>
                    <div className="seat-groupRows">
                      {group.rows.map((row) => (
                        <div className="seat-row" key={row}>
                          <div className="seat-rowLabel">{row}</div>
                          <div className="seat-rowSeats">
                            {dynamicSeatCols.map((col) => {
                              const key = `${row}${col}`;
                              const status = getSeatStatus(
                                key,
                                selectedSeats,
                                soldSeatSet,
                                unavailableSeatSet,
                                reservedSeatSet
                              );
                              const isBlocked =
                                status === "seat--reserved" ||
                                status === "seat--sold" ||
                                status === "seat--unavailable";
                              return (
                                <React.Fragment key={key}>
                                  <button
                                    type="button"
                                    className={`seat seat--cat-${group.key} ${status}`}
                                    aria-label={`Seat ${key}`}
                                    aria-pressed={status === "seat--selected"}
                                    disabled={isBlocked || pendingSeatSet.has(key)}
                                    onClick={() => toggleSeat(key)}
                                  >
                                    {key}
                                  </button>
                                </React.Fragment>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}

                <div className="seat-colLabels">
                  <div className="seat-colSpacer" />
                  {dynamicSeatCols.map((col) => (
                    <React.Fragment key={`col-${col}`}>
                      <div className="seat-colLabel">{col}</div>
                    </React.Fragment>
                  ))}
                </div>
              </div>

              <div className="seat-categoryLegend">
                <span className="seat-categoryLegendTitle">Seat Categories</span>
                {dynamicSeatGroups.map((group) => (
                  <span className="seat-legendItem" key={`cat-${group.key}`}>
                    <span className={`seat-legendBox category ${group.key}`} /> {group.label}
                  </span>
                ))}
              </div>

              <div className="seat-metaRow">
                <div className="seat-selectedInfo">
                  <strong>{selectedSeats.length} Selected Seats</strong>
                  <span className="seat-limit">Max {MAX_SELECTION}</span>
                </div>
                <div className="seat-selectedList">{renderSelectedSeats()}</div>
              </div>

              <div className="seat-legend">
                <span className="seat-legendItem">
                  <span className="seat-legendBox available" /> Available
                </span>
                <span className="seat-legendItem">
                  <span className="seat-legendBox selected" /> Selected
                </span>
                <span className="seat-legendItem">
                  <span className="seat-legendBox reserved" /> Reserved
                </span>
                <span className="seat-legendItem">
                  <span className="seat-legendBox sold" /> Sold Out
                </span>
                <span className="seat-legendItem">
                  <span className="seat-legendBox unavailable" /> Unavailable
                </span>
              </div>
            </div>
          </div>

          <div className="seat-summary">
            <div className="seat-summaryTitle">Selected Seats</div>
            <div className="seat-summarySeats">{renderSelectedSeats()}</div>

            {(selectedSeatLabels.length || seatLockTimedOut) ? (
              <div
                className={`seat-lockNotice${
                  seatLockTimedOut && !selectedSeatLabels.length
                    ? " seat-lockNotice--expired"
                    : seatLockInWarning
                      ? " seat-lockNotice--warning"
                      : ""
                }`}
              >
                <div className="seat-lockNoticeHeader">
                  <span className="seat-lockNoticeLabel">Seat Hold Timer</span>
                  <strong className="seat-lockNoticeTimer">
                    {selectedSeatLabels.length ? seatLockTimerLabel : "Expired"}
                  </strong>
                </div>
                <p className="seat-lockNoticeText">
                  {selectedSeatLabels.length
                    ? "Complete checkout before this timer ends or seats are released automatically."
                    : "Your previous seat hold expired. Reselect seats to continue."}
                </p>
              </div>
            ) : null}

            <div className="seat-pricingIndicator">
              {pricingPreview?.pricing_indicator || "Price may increase as seats fill."}
            </div>
            {pricingLoading ? <div className="seat-pricingLoading">Calculating dynamic price...</div> : null}
            {pricingError ? <div className="seat-pricingError">{pricingError}</div> : null}

            <div className="seat-summarySubTitle">Current Category Prices</div>
            {Object.keys(dynamicByCategory).length ? (
              Object.entries(dynamicByCategory).map(([categoryKey, value]) => (
                <div className="seat-priceRow" key={`category-price-${categoryKey}`}>
                  <span>
                    {formatSeatCategoryLabel(categoryKey)}
                    <span className="seat-muted">
                      Base Npr {formatNpr(value?.base_price)}
                    </span>
                  </span>
                  <span>Npr {formatNpr(value?.dynamic_price)}</span>
                </div>
              ))
            ) : (
              <div className="seat-pricingHint">Select seats to load category-wise dynamic prices.</div>
            )}

            <div className="seat-priceRow">
              <span>Base Subtotal</span>
              <span>Npr {formatNpr(dynamicBaseSubtotal)}</span>
            </div>
            {dynamicRuleAdjustment !== 0 ? (
              <div className={`seat-priceRow ${dynamicRuleAdjustment < 0 ? "seat-discountRow" : ""}`}>
                <span>Rule Adjustments</span>
                <span>{dynamicRuleAdjustment > 0 ? "+" : ""}Npr {formatNpr(dynamicRuleAdjustment)}</span>
              </div>
            ) : null}
            {dynamicOccupancyAdjustment !== 0 ? (
              <div className={`seat-priceRow ${dynamicOccupancyAdjustment < 0 ? "seat-discountRow" : ""}`}>
                <span>Occupancy Surge/Discount</span>
                <span>{dynamicOccupancyAdjustment > 0 ? "+" : ""}Npr {formatNpr(dynamicOccupancyAdjustment)}</span>
              </div>
            ) : null}

            {priceLock?.expires_at ? (
              <div className="seat-priceLockMeta">
                Price locked until {formatTimeFromIso(priceLock.expires_at)}
              </div>
            ) : null}

            <div className="seat-total">
              <span>Total Payment:</span>
              <span>Npr {formatNpr(totalPrice)}</span>
            </div>

            <button
              className="seat-payBtn"
              type="button"
              onClick={handleProceed}
              disabled={totalSeats === 0 || proceeding || pricingLoading}
            >
              {proceeding ? "Checking Food..." : "Proceed"}
            </button>
            <button
              className="seat-cancelBtn"
              type="button"
              onClick={handleCancelSelection}
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function parseSeatLockDeadlines(rawLocks) {
  if (!rawLocks || typeof rawLocks !== "object") {
    return {};
  }

  const nowMs = Date.now();
  const output = {};
  Object.entries(rawLocks).forEach(([seat, value]) => {
    const label = normalizeSeatLabel(seat);
    const deadline = parseIsoToEpochMs(value);
    if (!label || !Number.isFinite(deadline) || deadline <= nowMs) {
      return;
    }
    output[label] = deadline;
  });
  return output;
}

function parseIsoToEpochMs(value) {
  if (!value) return null;
  const parsed = new Date(value);
  const epoch = parsed.getTime();
  return Number.isFinite(epoch) ? epoch : null;
}

function formatCountdown(value) {
  const totalSeconds = Math.max(0, Number(value) || 0);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatSeatLabelList(labels, maxVisible = 3) {
  const normalized = Array.from(
    new Set(
      (Array.isArray(labels) ? labels : [])
        .map((seat) => normalizeSeatLabel(seat))
        .filter(Boolean)
    )
  ).sort((a, b) => seatSortKey(a) - seatSortKey(b));

  if (!normalized.length) return "selected seats";
  if (normalized.length <= maxVisible) return normalized.join(", ");
  return `${normalized.slice(0, maxVisible).join(", ")} +${normalized.length - maxVisible} more`;
}

function ensureUniqueGroupRows(groups) {
  const input = Array.isArray(groups) ? groups : [];
  const usedRows = new Set();

  return input.map((group) => {
    const groupRows = Array.isArray(group?.rows) ? group.rows : [];
    const normalizedRows = groupRows
      .map((row) => String(row || "").trim().toUpperCase())
      .filter(Boolean);

    const uniqueRows = normalizedRows.map((row) => {
      if (!usedRows.has(row)) {
        usedRows.add(row);
        return row;
      }
      const next = nextAvailableRowLabel(usedRows);
      usedRows.add(next);
      return next;
    });

    return {
      ...group,
      rows: uniqueRows,
    };
  });
}

function nextAvailableRowLabel(usedRows) {
  let index = 0;
  while (index < 2000) {
    const label = rowLabelFromIndex(index);
    if (!usedRows.has(label)) {
      return label;
    }
    index += 1;
  }
  return `ROW${usedRows.size + 1}`;
}

function rowLabelFromIndex(index) {
  let value = Number(index) + 1;
  let label = "";
  while (value > 0) {
    const remainder = (value - 1) % 26;
    label = String.fromCharCode(65 + remainder) + label;
    value = Math.floor((value - 1) / 26);
  }
  return label;
}

function getSeatStatus(
  key,
  selectedSeats,
  soldSeatSet = new Set(),
  unavailableSeatSet = new Set(),
  reservedSeatSet = new Set()
) {
  if (selectedSeats.includes(key)) return "seat--selected";
  if (reservedSeatSet.has(normalizeSeatLabel(key))) return "seat--reserved";
  if (soldSeatSet.has(normalizeSeatLabel(key))) return "seat--sold";
  if (unavailableSeatSet.has(normalizeSeatLabel(key))) return "seat--unavailable";
  return "seat--available";
}

function normalizeSeatLabel(value) {
  return String(value || "")
    .replace(/\s+/g, "")
    .toUpperCase()
    .trim();
}

function seatSortKey(value) {
  const label = normalizeSeatLabel(value);
  const match = label.match(/^([A-Z]+)(\d+)$/);
  if (!match) return Number.MAX_SAFE_INTEGER;
  const row = match[1];
  const seatNumber = Number(match[2]) || 0;
  const rowScore = row
    .split("")
    .reduce((sum, char) => (sum * 26) + (char.charCodeAt(0) - 64), 0);
  return rowScore * 1000 + seatNumber;
}

function coerceInt(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : null;
}

function toApiTime(value) {
  if (!value) return "";
  const text = String(value).trim();
  if (!text) return "";

  const amPmMatch = text.match(/^(\d{1,2}):(\d{2})\s*([AaPp][Mm])$/);
  if (amPmMatch) {
    let hour = Number(amPmMatch[1]);
    const minutes = Number(amPmMatch[2]);
    const period = amPmMatch[3].toUpperCase();
    if (Number.isNaN(hour) || Number.isNaN(minutes)) return "";
    if (period === "PM" && hour < 12) hour += 12;
    if (period === "AM" && hour === 12) hour = 0;
    return `${String(hour).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
  }

  const hourMinMatch = text.match(/^(\d{1,2}):(\d{2})$/);
  if (hourMinMatch) {
    const hour = Number(hourMinMatch[1]);
    const minutes = Number(hourMinMatch[2]);
    if (Number.isNaN(hour) || Number.isNaN(minutes)) return "";
    return `${String(hour).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
  }

  return "";
}

function formatVenueDate(value) {
  const iso = normalizeDateValue(value);
  if (!iso) return "";
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatChipDate(value) {
  const iso = normalizeDateValue(value);
  if (!iso) return "";
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
  });
}

function findMatchingShow(shows, movie, vendor, dateValue, timeValue) {
  const list = Array.isArray(shows) ? shows : [];
  if (!list.length) return null;

  const normalizedDate = normalizeDateValue(dateValue);
  const normalizedDisplayTime = formatTime(timeValue);
  const normalizedApiTime = toApiTime(timeValue);

  return (
    list.find((show) => {
      if (!show) return false;
      if (!matchesMovie(show, movie)) return false;
      if (!matchesVendor(show, vendor)) return false;

      const showDate = normalizeDateValue(show.date || show.show_date || show.showDate);
      if (normalizedDate && showDate && showDate !== normalizedDate) {
        return false;
      }

      if (!normalizedDisplayTime && !normalizedApiTime) {
        return true;
      }

      const showRawTime = String(
        show.start || show.start_time || show.startTime || ""
      ).trim();
      if (!showRawTime) return false;

      if (normalizedDisplayTime && formatTime(showRawTime) === normalizedDisplayTime) {
        return true;
      }
      if (normalizedApiTime && toApiTime(showRawTime) === normalizedApiTime) {
        return true;
      }
      return false;
    }) || null
  );
}

function getStoredUser() {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem("user") || localStorage.getItem("user");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function safeUseAppContext() {
  try {
    return useAppContext?.();
  } catch {
    return null;
  }
}

function buildSeatShowtimes(shows, movie, vendor, preferredDate, preferredTime) {
  const list = Array.isArray(shows) ? shows : [];
  const filtered = list.filter((show) => {
    if (!show) return false;
    if (!matchesMovie(show, movie)) return false;
    if (!matchesVendor(show, vendor)) return false;
    return true;
  });

  if (!filtered.length) {
    return {
      dates: [],
      times: [],
      activeDate: "",
      venueLabel: resolveVendorLabel(vendor),
      subtitle: "",
    };
  }

  const availableDates = [];
  const dateSet = new Set();
  filtered.forEach((show) => {
    const dateValue = normalizeDateValue(show.date || show.show_date || show.showDate);
    if (!dateValue || dateSet.has(dateValue)) return;
    dateSet.add(dateValue);
    availableDates.push(dateValue);
  });

  const dates = availableDates
    .slice()
    .sort((a, b) => new Date(a).getTime() - new Date(b).getTime());

  const desiredDate = normalizeDateValue(preferredDate);
  const todayIso = new Date().toISOString().slice(0, 10);
  let focusDate = "";
  if (desiredDate && dateSet.has(desiredDate)) {
    focusDate = desiredDate;
  } else if (dateSet.has(todayIso)) {
    focusDate = todayIso;
  } else if (availableDates.length) {
    focusDate = availableDates
      .slice()
      .sort((a, b) => new Date(a).getTime() - new Date(b).getTime())[0];
  }

  const timeSet = new Set();
  filtered.forEach((show) => {
    const showDate = normalizeDateValue(show.date || show.show_date || show.showDate);
    if (focusDate && showDate && showDate !== focusDate) return;
    const rawTime = String(show.start || show.start_time || show.startTime || "").trim();
    if (!rawTime) return;
    timeSet.add(formatTime(rawTime));
  });

  const times = Array.from(timeSet).filter(Boolean).sort((a, b) => (a > b ? 1 : -1));

  const venueLabel =
    resolveVendorLabel(vendor) ||
    String(
      filtered[0]?.vendor ||
        filtered[0]?.vendor_name ||
        filtered[0]?.vendorName ||
        filtered[0]?.cinema ||
        ""
    ).trim();

  return {
    dates,
    times,
    activeDate: focusDate,
    venueLabel,
    subtitle: buildSubtitle(focusDate),
  };
}

function matchesMovie(show, movie) {
  if (!movie) return true;
  const movieId = String(movie?.id || movie?._id || "").trim();
  const showMovieId = String(show.movieId || show.movie_id || "").trim();
  if (movieId && showMovieId && movieId === showMovieId) return true;
  const movieTitle = normalizeText(movie?.title || movie?.name);
  if (!movieTitle) return true;
  const showTitle = normalizeText(
    show.movie || show.movie_title || show.title || show.name
  );
  return movieTitle === showTitle;
}

function matchesVendor(show, vendor) {
  if (!vendor) return true;
  const vendorId = String(vendor?.id || vendor?.vendorId || vendor?.vendor_id || "").trim();
  const showVendorId = String(show.vendorId || show.vendor_id || "").trim();
  if (vendorId && showVendorId && vendorId === showVendorId) return true;
  const vendorName = normalizeText(
    vendor?.name || vendor?.vendor || vendor?.cinemaName || vendor?.cinema || vendor
  );
  if (!vendorName) return true;
  const showVendorName = normalizeText(
    show.vendor || show.vendor_name || show.vendorName || show.cinema || show.cinemaName
  );
  return vendorName === showVendorName;
}

function resolveVendorLabel(vendor) {
  if (!vendor) return "";
  if (typeof vendor === "string") return vendor;
  return (
    vendor.name ||
    vendor.vendor ||
    vendor.cinemaName ||
    vendor.cinema ||
    ""
  );
}

function normalizeText(value) {
  return String(value || "").trim().toLowerCase();
}

function normalizeDateValue(value) {
  if (!value) return "";
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value.toISOString().slice(0, 10);
  }
  const text = String(value).trim();
  if (!text) return "";
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
  const date = new Date(text);
  if (!Number.isNaN(date.getTime())) return date.toISOString().slice(0, 10);
  return "";
}

function buildSubtitle(dateValue) {
  if (!dateValue) return "";
  const date = new Date(dateValue);
  if (Number.isNaN(date.getTime())) return `Shows on ${dateValue}`;
  const today = new Date();
  const isToday = date.toDateString() === today.toDateString();
  if (isToday) return "Shows Today";
  return `Shows on ${date.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
  })}`;
}

function formatTime(value) {
  if (!value) return "";
  const text = String(value).trim();
  if (!text) return "";
  if (text.toLowerCase().includes("am") || text.toLowerCase().includes("pm")) return text;
  const [hours, minutes] = text.split(":").map((part) => Number(part));
  if (Number.isNaN(hours) || Number.isNaN(minutes)) return text;
  const period = hours >= 12 ? "PM" : "AM";
  const adjusted = hours % 12 || 12;
  return `${String(adjusted).padStart(2, "0")}:${String(minutes).padStart(2, "0")} ${period}`;
}

function buildBookingPayload(
  movieId,
  cinemaId,
  dateValue,
  timeValue,
  showId,
  hall,
  seats
) {
  const payload = {
    movie_id: movieId,
    cinema_id: cinemaId,
    date: dateValue,
    time: timeValue,
    selected_seats: seats,
  };
  if (showId) payload.show_id = showId;
  if (hall) payload.hall = hall;
  return payload;
}

function formatNpr(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "0.00";
  return numeric.toFixed(2);
}

function formatSeatCategoryLabel(value) {
  const key = String(value || "").trim().toLowerCase();
  if (!key) return "Category";
  if (key === "vip") return "VIP";
  return key.slice(0, 1).toUpperCase() + key.slice(1);
}

function formatTimeFromIso(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

const fallbackShows = [
  { _id: "1", title: "Hami Teen Bhai", poster: gharjwai },
  { _id: "2", title: "Avengers", poster: avengers },
  { _id: "3", title: "Degree Maila", poster: degreemaila },
  { _id: "4", title: "Balidan", poster: balidan },
];
