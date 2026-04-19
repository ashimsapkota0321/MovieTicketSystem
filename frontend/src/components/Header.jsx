import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Bell, ChevronDown, Search, User } from "lucide-react";
import { useAppContext } from "../context/Appcontext";
import api from "../api/api";
import AdultWarningModal from "./AdultWarningModal";
import UserNotificationSidebar from "./UserNotificationSidebar";
import { buildMetaLine, getMovieRatingLabel, isAdultRating, toText } from "../lib/showUtils";
import { fetchNotifications } from "../lib/catalogApi";
import {
  clearAuthSession,
  clearStoredRoleData,
  getAuthSession,
  getStoredRoleData,
} from "../lib/authSession";
import logo from "../images/logo.png";
import "../css/layout.css";

const formatDateLabel = (value) => {
  if (!value) return "";
  const parts = String(value).split("-").map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return value;
  const [year, month, day] = parts;
  const date = new Date(year, month - 1, day);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
};

const formatTimeLabel = (value) => {
  if (!value) return "";
  const parts = String(value).split(":").map(Number);
  if (parts.length < 2 || parts.some(Number.isNaN)) return value;
  const [hour, minute] = parts;
  const time = new Date();
  time.setHours(hour, minute, 0, 0);
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(time);
};

const mapCinemaOptions = (items) =>
  (items || []).map((cinema) => ({
    value: String(cinema.id),
    label:
      cinema.name || cinema.theatre || cinema.city || `Cinema ${cinema.id}`,
  }));

const mapMovieOptions = (items) =>
  (items || []).map((movie) => ({
    value: String(movie.id),
    label: movie.title || `Movie ${movie.id}`,
  }));

const mapDateOptions = (items) =>
  (items || []).map((date) => ({
    value: String(date),
    label: formatDateLabel(date),
  }));

const mapTimeOptions = (items) =>
  (items || []).map((time) => ({
    value: String(time),
    label: formatTimeLabel(time),
  }));

export default function Header() {
  const navigate = useNavigate();
  const location = useLocation();
  const path = location.pathname;
  const headerRef = useRef(null);
  const bookingRef = useRef(null);
  const searchRef = useRef(null);
  const ctx = safeUseAppContext();
  const appSelectedLocation = ctx?.selectedLocation || "";
  const selectedLocationLabel = appSelectedLocation || "All Cities";
  const setAppSelectedLocation = ctx?.setSelectedLocation;
  const contextMovies = ctx?.movies ?? [];

  const [scrolled, setScrolled] = useState(false);
  const [locationOpen, setLocationOpen] = useState(false);
  const [openSelect, setOpenSelect] = useState(null);
  const [bookingMode, setBookingMode] = useState("cinema");
  const [selectedCinemaId, setSelectedCinemaId] = useState("");
  const [selectedMovieId, setSelectedMovieId] = useState("");
  const [selectedDate, setSelectedDate] = useState("");
  const [selectedTime, setSelectedTime] = useState("");
  const [allCinemas, setAllCinemas] = useState([]);
  const [allMovies, setAllMovies] = useState([]);
  const [cinemasForMovie, setCinemasForMovie] = useState([]);
  const [moviesForCinema, setMoviesForCinema] = useState([]);
  const [dateOptions, setDateOptions] = useState([]);
  const [timeOptions, setTimeOptions] = useState([]);
  const [locationOptions, setLocationOptions] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchGenre, setSearchGenre] = useState("All");
  const [storedUser, setStoredUser] = useState(() => getStoredUser());
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notificationSidebarOpen, setNotificationSidebarOpen] = useState(false);
  const [adultConfirmOpen, setAdultConfirmOpen] = useState(false);
  const [pendingBookingState, setPendingBookingState] = useState(null);
  const isCinemaSelected = Boolean(selectedCinemaId);
  const isMovieSelected = Boolean(selectedMovieId);
  const isDateSelected = Boolean(selectedDate);
  const cinemaLocked = bookingMode === "movie" && !isMovieSelected;
  const movieLocked = bookingMode === "cinema" && !isCinemaSelected;
  const dateLocked = !(isCinemaSelected && isMovieSelected);
  const timeLocked = !isDateSelected;
  const isBookingReady = Boolean(
    selectedCinemaId && selectedMovieId && selectedDate && selectedTime
  );
  const showtimes = ctx?.showtimes ?? [];
  const user = ctx?.user ?? storedUser;
  const displayName = getUserDisplayName(user);
  const username = getUserUsername(user);
  const initials = getUserInitials(displayName || username);
  const avatarSrc = getUserAvatar(user);

  const locations = Array.from(
    new Set([
      ...locationOptions,
      ...(appSelectedLocation ? [appSelectedLocation] : []),
    ])
  );
  const cinemaOptions =
    bookingMode === "movie" && selectedMovieId ? cinemasForMovie : allCinemas;
  const movieOptions =
    bookingMode === "cinema" && selectedCinemaId ? moviesForCinema : allMovies;
  const selectedCinemaOption =
    cinemaOptions.find((option) => String(option.value) === String(selectedCinemaId)) ||
    allCinemas.find((option) => String(option.value) === String(selectedCinemaId)) ||
    null;
  const selectedMovieOption =
    movieOptions.find((option) => String(option.value) === String(selectedMovieId)) ||
    allMovies.find((option) => String(option.value) === String(selectedMovieId)) ||
    null;
  const selectedMovieCatalog = useMemo(() => {
    if (!selectedMovieId) return null;
    return (
      contextMovies.find((item) => String(item?.id || item?._id || "") === String(selectedMovieId)) ||
      null
    );
  }, [contextMovies, selectedMovieId]);
  const normalizedSearchTerm = searchTerm.trim().toLowerCase();

  const titleMatchedMovies = useMemo(() => {
    if (!normalizedSearchTerm) return [];
    return contextMovies
      .filter((movie) => {
        const title = String(movie?.title || movie?.name || "").toLowerCase();
        return title.includes(normalizedSearchTerm);
      })
      .slice(0, 24);
  }, [contextMovies, normalizedSearchTerm]);

  const searchGenres = useMemo(() => {
    if (!titleMatchedMovies.length) return ["All"];
    const genreSet = new Set();
    titleMatchedMovies.forEach((movie) => {
      splitGenres(movie?.genre || movie?.genres || movie?.category).forEach((genre) => {
        genreSet.add(genre);
      });
    });
    return ["All", ...Array.from(genreSet).slice(0, 8)];
  }, [titleMatchedMovies]);

  const searchResults = useMemo(() => {
    if (searchGenre === "All") return titleMatchedMovies.slice(0, 12);
    const target = String(searchGenre || "").toLowerCase();
    return titleMatchedMovies
      .filter((movie) =>
        splitGenres(movie?.genre || movie?.genres || movie?.category)
          .map((item) => item.toLowerCase())
          .includes(target)
      )
      .slice(0, 12);
  }, [titleMatchedMovies, searchGenre]);

  const shouldShowSearchPanel = searchOpen && Boolean(normalizedSearchTerm);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const root = document.documentElement;
    const updateHeaderOffset = () => {
      const height = Math.ceil(headerRef.current?.getBoundingClientRect().height || 0);
      root.style.setProperty("--wf2-header-offset", `${height}px`);
    };

    updateHeaderOffset();
    window.addEventListener("resize", updateHeaderOffset);

    let resizeObserver = null;
    if (typeof window.ResizeObserver !== "undefined" && headerRef.current) {
      resizeObserver = new window.ResizeObserver(updateHeaderOffset);
      resizeObserver.observe(headerRef.current);
    }

    return () => {
      window.removeEventListener("resize", updateHeaderOffset);
      if (resizeObserver) resizeObserver.disconnect();
      root.style.removeProperty("--wf2-header-offset");
    };
  }, []);

  useEffect(() => {
    let active = true;

    const loadLocationOptions = async () => {
      try {
        const response = await api.get("/api/cinemas/");
        if (!active) return;
        const vendors = Array.isArray(response?.data?.vendors)
          ? response.data.vendors
          : [];
        const cities = Array.from(
          new Set(
            vendors
              .map((vendor) => String(vendor?.city || "").trim())
              .filter(Boolean)
          )
        ).sort((a, b) => a.localeCompare(b));
        setLocationOptions(cities);
      } catch {
        if (!active) return;
        setLocationOptions([]);
      }
    };

    loadLocationOptions();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (bookingRef.current && !bookingRef.current.contains(event.target)) {
        setOpenSelect(null);
      }
      if (searchRef.current && !searchRef.current.contains(event.target)) {
        setSearchOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    setSearchOpen(false);
  }, [path]);

  useEffect(() => {
    setSearchGenre("All");
  }, [normalizedSearchTerm]);

  useEffect(() => {
    const disabledMap = {
      cinema: cinemaLocked,
      movie: movieLocked,
      date: dateLocked,
      time: timeLocked,
    };
    if (openSelect && disabledMap[openSelect]) {
      setOpenSelect(null);
    }
  }, [openSelect, cinemaLocked, movieLocked, dateLocked, timeLocked]);

  useEffect(() => {
    setSelectedCinemaId("");
    setSelectedMovieId("");
    setSelectedDate("");
    setSelectedTime("");
    setDateOptions([]);
    setTimeOptions([]);
    setOpenSelect(null);
  }, [bookingMode]);

  useEffect(() => {
    let active = true;
    const loadInitialOptions = async () => {
      try {
        const [cinemaResponse, movieResponse] = await Promise.all([
          api.get("/api/booking/cinemas/", {
            params: appSelectedLocation ? { city: appSelectedLocation } : undefined,
          }),
          api.get("/api/booking/movies/", {
            params: appSelectedLocation ? { city: appSelectedLocation } : undefined,
          }),
        ]);
        if (!active) return;
        setAllCinemas(mapCinemaOptions(cinemaResponse?.data?.cinemas));
        setAllMovies(mapMovieOptions(movieResponse?.data?.movies));
      } catch (error) {
        if (!active) return;
        setAllCinemas([]);
        setAllMovies([]);
      }
    };
    loadInitialOptions();
    return () => {
      active = false;
    };
  }, [appSelectedLocation]);

  useEffect(() => {
    if (bookingMode === "cinema") {
      setSelectedMovieId("");
    }
    setSelectedDate("");
    setSelectedTime("");
    setDateOptions([]);
    setTimeOptions([]);

    if (!selectedCinemaId) {
      setMoviesForCinema([]);
      return;
    }

    let active = true;
    const loadMoviesForCinema = async () => {
      try {
        const response = await api.get("/api/booking/movies/", {
          params: {
            cinema_id: selectedCinemaId,
            ...(appSelectedLocation ? { city: appSelectedLocation } : {}),
          },
        });
        if (!active) return;
        setMoviesForCinema(mapMovieOptions(response?.data?.movies));
      } catch (error) {
        if (!active) return;
        setMoviesForCinema([]);
      }
    };
    loadMoviesForCinema();
    return () => {
      active = false;
    };
  }, [selectedCinemaId, bookingMode, appSelectedLocation]);

  useEffect(() => {
    if (bookingMode === "movie") {
      setSelectedCinemaId("");
    }
    setSelectedDate("");
    setSelectedTime("");
    setDateOptions([]);
    setTimeOptions([]);

    if (!selectedMovieId) {
      setCinemasForMovie([]);
      return;
    }

    let active = true;
    const loadCinemasForMovie = async () => {
      try {
        const response = await api.get("/api/booking/cinemas/", {
          params: {
            movie_id: selectedMovieId,
            ...(appSelectedLocation ? { city: appSelectedLocation } : {}),
          },
        });
        if (!active) return;
        setCinemasForMovie(mapCinemaOptions(response?.data?.cinemas));
      } catch (error) {
        if (!active) return;
        setCinemasForMovie([]);
      }
    };
    loadCinemasForMovie();
    return () => {
      active = false;
    };
  }, [selectedMovieId, bookingMode, appSelectedLocation]);

  useEffect(() => {
    if (!selectedCinemaId || !selectedMovieId) {
      setDateOptions([]);
      setSelectedDate("");
      setTimeOptions([]);
      setSelectedTime("");
      return;
    }

    let active = true;
    const loadDates = async () => {
      try {
        const response = await api.get("/api/booking/dates/", {
          params: {
            cinema_id: selectedCinemaId,
            movie_id: selectedMovieId,
            ...(appSelectedLocation ? { city: appSelectedLocation } : {}),
          },
        });
        if (!active) return;
        setDateOptions(mapDateOptions(response?.data?.dates));
      } catch (error) {
        if (!active) return;
        setDateOptions([]);
      }
    };
    loadDates();
    return () => {
      active = false;
    };
  }, [selectedCinemaId, selectedMovieId, appSelectedLocation]);

  useEffect(() => {
    if (!selectedCinemaId || !selectedMovieId || !selectedDate) {
      setTimeOptions([]);
      setSelectedTime("");
      return;
    }

    let active = true;
    const loadTimes = async () => {
      try {
        const response = await api.get("/api/booking/times/", {
          params: {
            cinema_id: selectedCinemaId,
            movie_id: selectedMovieId,
            date: selectedDate,
            ...(appSelectedLocation ? { city: appSelectedLocation } : {}),
          },
        });
        if (!active) return;
        setTimeOptions(mapTimeOptions(response?.data?.times));
      } catch (error) {
        if (!active) return;
        setTimeOptions([]);
      }
    };
    loadTimes();
    return () => {
      active = false;
    };
  }, [selectedCinemaId, selectedMovieId, selectedDate, appSelectedLocation]);

  useEffect(() => {
    const handleUserUpdate = () => {
      setStoredUser(getStoredUser());
    };
    window.addEventListener("storage", handleUserUpdate);
    window.addEventListener("mt:user-updated", handleUserUpdate);
    return () => {
      window.removeEventListener("storage", handleUserUpdate);
      window.removeEventListener("mt:user-updated", handleUserUpdate);
    };
  }, []);

  useEffect(() => {
    let active = true;
    const auth = getAuthSession("customer");
    if (!user || !auth?.token) {
      setNotifications([]);
      setUnreadCount(0);
      return () => {
        active = false;
      };
    }

    const loadNotifications = async () => {
      try {
        const payload = await fetchNotifications({ limit: 6 });
        if (!active) return;
        setNotifications(Array.isArray(payload?.notifications) ? payload.notifications : []);
        setUnreadCount(Number(payload?.unread_count || 0));
      } catch {
        if (!active) return;
        setNotifications([]);
        setUnreadCount(0);
      }
    };

    const handleNotificationUpdate = () => {
      loadNotifications();
    };

    loadNotifications();
    window.addEventListener("mt:notifications-updated", handleNotificationUpdate);
    return () => {
      active = false;
      window.removeEventListener("mt:notifications-updated", handleNotificationUpdate);
    };
  }, [user, path]);

  const matchedShowId = useMemo(() => {
    if (!selectedCinemaId || !selectedMovieId || !selectedDate || !selectedTime) {
      return null;
    }
    return findMatchingShowId(
      showtimes,
      selectedCinemaId,
      selectedMovieId,
      selectedDate,
      selectedTime
    );
  }, [showtimes, selectedCinemaId, selectedMovieId, selectedDate, selectedTime]);

  useEffect(() => {
    if (!selectedCinemaId) return;
    const hasCinema = cinemaOptions.some(
      (option) => String(option.value) === String(selectedCinemaId)
    );
    if (!hasCinema) {
      setSelectedCinemaId("");
      setSelectedDate("");
      setSelectedTime("");
      setDateOptions([]);
      setTimeOptions([]);
    }
  }, [cinemaOptions, selectedCinemaId]);

  useEffect(() => {
    if (!selectedMovieId) return;
    const hasMovie = movieOptions.some(
      (option) => String(option.value) === String(selectedMovieId)
    );
    if (!hasMovie) {
      setSelectedMovieId("");
      setSelectedDate("");
      setSelectedTime("");
      setDateOptions([]);
      setTimeOptions([]);
    }
  }, [movieOptions, selectedMovieId]);

  useEffect(() => {
    if (!selectedDate) return;
    const hasDate = dateOptions.some(
      (option) => String(option.value) === String(selectedDate)
    );
    if (!hasDate) {
      setSelectedDate("");
      setSelectedTime("");
      setTimeOptions([]);
    }
  }, [dateOptions, selectedDate]);

  useEffect(() => {
    if (!selectedTime) return;
    const hasTime = timeOptions.some(
      (option) => String(option.value) === String(selectedTime)
    );
    if (!hasTime) {
      setSelectedTime("");
    }
  }, [timeOptions, selectedTime]);

  const handleLogout = () => {
    const auth = getAuthSession("customer");
    const scope = auth?.scope === "session" ? "session" : "local";
    clearAuthSession({ role: "customer", scope });
    clearStoredRoleData("customer", { scope });
    setStoredUser(null);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("mt:user-updated"));
    }
    navigate("/login");
  };

  const navigateToBookingState = (bookingState) => {
    if (!bookingState) return;
    navigate("/booking", { state: bookingState });
  };

  const handleBuyNow = () => {
    if (!isBookingReady) return;

    const movieState = {
      id: coerceNumber(selectedMovieId),
      title: selectedMovieOption?.label || "Movie",
      rating: selectedMovieCatalog?.rating || "",
      certificate: selectedMovieCatalog?.certificate || "",
      censor: selectedMovieCatalog?.censor || "",
      classification: selectedMovieCatalog?.classification || "",
      ageRating: selectedMovieCatalog?.ageRating || "",
    };

    const bookingState = {
      movie: movieState,
      vendor: {
        id: coerceNumber(selectedCinemaId),
        name: selectedCinemaOption?.label || "Cinema",
      },
      showId: matchedShowId,
      date: selectedDate,
      time: selectedTime,
    };

    if (isAdultRating(getMovieRatingLabel(movieState))) {
      setPendingBookingState(bookingState);
      setAdultConfirmOpen(true);
      return;
    }

    navigateToBookingState(bookingState);
  };

  const SelectField = ({ id, label, value, options, onChange, disabled, placeholder }) => {
    const isOpen = !disabled && openSelect === id;
    const isPlaceholder = !value;
    const menuOptions = options || [];
    const selectedOption = menuOptions.find(
      (option) => String(option.value) === String(value)
    );
    const displayValue = isPlaceholder
      ? placeholder
      : selectedOption?.label || placeholder;

    const handleToggle = () => {
      if (disabled) return;
      setOpenSelect(isOpen ? null : id);
    };

    const handleSelect = (optionValue) => {
      onChange(optionValue);
      setOpenSelect(null);
    };

    return (
      <div className="wf2-controlGroup">
        <div className="wf2-selectWrap">
          <button
            type="button"
            className={`wf2-selectTrigger ${isPlaceholder ? "wf2-selectPlaceholder" : ""} ${isOpen ? "wf2-selectTriggerOpen" : ""} ${disabled ? "wf2-selectTriggerDisabled" : ""}`}
            onClick={handleToggle}
            disabled={disabled}
            aria-label={label}
          >
            <span>{displayValue}</span>
            <ChevronDown size={18} />
          </button>
          {isOpen ? (
            <div className="wf2-selectMenu">
              {menuOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`wf2-selectOption ${String(option.value) === String(value) ? "wf2-selectOptionActive" : ""}`}
                  onClick={() => handleSelect(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    );
  };

  return (
    <header ref={headerRef} className={`wf2-header ${scrolled ? "wf2-headerScrolled" : ""}`}>
      <div className="wf2-container wf2-headerTop">
        <div className="wf2-headerLeft">
          <img
            src={logo}
            alt="Mero Ticket Logo"
            className="wf2-brandImg"
            role="button"
            tabIndex={0}
            onClick={() => navigate("/")}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") navigate("/"); }}
          />
          <div className="wf2-locationDropdown">
            <button
              className="wf2-locationBtn"
              onClick={() => setLocationOpen((prev) => !prev)}
            >
              <span className="wf2-locationIcon" aria-hidden="true">
                <svg viewBox="0 0 24 24" role="presentation">
                  <path
                    className="wf2-locationPin"
                    fillRule="evenodd"
                    d="M12 2c-4.42 0-8 3.58-8 8 0 6.02 8 12 8 12s8-5.98 8-12c0-4.42-3.58-8-8-8zm0 11a3 3 0 1 1 0-6 3 3 0 0 1 0 6z"
                  />
                  <circle className="wf2-locationDot" cx="19" cy="5" r="3" />
                </svg>
              </span>
                <span>{selectedLocationLabel}</span>
              <ChevronDown size={18} />
            </button>
          </div>
        </div>

        <div className="wf2-headerNav">
          <div className="wf2-searchArea" ref={searchRef}>
            <div className="wf2-search" role="search">
              <Search size={18} />
              <input
                type="text"
                placeholder="Search movies..."
                value={searchTerm}
                onFocus={() => setSearchOpen(true)}
                onChange={(event) => {
                  setSearchTerm(event.target.value);
                  setSearchOpen(true);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    setSearchOpen(false);
                    return;
                  }
                  if (event.key === "Enter" && searchResults[0]) {
                    const movie = searchResults[0];
                    setSearchOpen(false);
                    navigate(
                      `/movie/${movie?._id || movie?.id || encodeURIComponent(movie?.title || movie?.name || "")}`,
                      { state: { movie } }
                    );
                  }
                }}
                aria-label="Search movies"
              />
            </div>

            {shouldShowSearchPanel ? (
              <div className="wf2-searchPanel" role="dialog" aria-label="Search results">
                <div className="wf2-searchPanelRow">
                  <div className="wf2-searchPanelLabel">Search Titles Related To</div>
                  <div className="wf2-searchGenreChips">
                    {searchGenres.map((genre) => (
                      <button
                        key={genre}
                        type="button"
                        className={`wf2-searchGenreChip ${searchGenre === genre ? "wf2-searchGenreChipActive" : ""}`}
                        onClick={() => setSearchGenre(genre)}
                      >
                        {genre}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="wf2-searchResultHead">
                  <div className="wf2-searchResultTitle">Search Result</div>
                  <div className="wf2-searchResultCount">
                    {searchResults.length} {searchResults.length === 1 ? "Movie" : "Movies"}
                  </div>
                </div>
                {searchResults.length ? (
                  <div className="wf2-searchResultGrid">
                    {searchResults.map((movie) => {
                      const title = movie?.title || movie?.name || "Untitled Movie";
                      const ratingLabel =
                        toText(
                          movie?.censor ||
                          movie?.rating ||
                          movie?.certificate ||
                          movie?.classification
                        ) || "PG";
                      const metaLine = buildMetaLine(movie);
                      const isAdult = isAdultRating(ratingLabel);
                      const statusLabel = String(movie?.status || movie?.listingStatus || "Now Showing");
                      return (
                        <button
                          key={movie?._id || movie?.id || title}
                          type="button"
                          className="wf2-searchCard"
                          onClick={() => {
                            setSearchOpen(false);
                            navigate(
                              `/movie/${movie?._id || movie?.id || encodeURIComponent(title)}`,
                              { state: { movie } }
                            );
                          }}
                        >
                          <div className="wf2-searchCardPoster">
                            <img src={getMoviePoster(movie)} alt={title} loading="lazy" decoding="async" />
                            <div className="wf2-searchCardRibbon">{statusLabel}</div>
                            <div className={`wf2-searchRatingBadge ${isAdult ? "wf2-searchRatingBadgeAdult" : ""}`}>
                              {ratingLabel}
                            </div>
                          </div>
                          <div className="wf2-searchCardBody">
                            <div className="wf2-searchCardTitle">{title}</div>
                            <div className="wf2-searchCardMeta">{metaLine}</div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="wf2-searchEmpty">No matching movies found for "{searchTerm.trim()}".</div>
                )}
              </div>
            ) : null}
          </div>
          <nav className="wf2-navPillsTop">
            <button
              className={`wf2-pillTop ${isActive(path, "/") ? "wf2-pillTopActive" : ""}`}
              onClick={() => navigate("/")}
            >
              HOME
            </button>
            <div className="wf2-navItem wf2-navDropdown">
              <button
                className={`wf2-pillTop ${isActive(path, "/movies") ? "wf2-pillTopActive" : ""}`}
                onClick={() => navigate("/movies")}
                type="button"
              >
                MOVIES
              </button>
              <div className="wf2-navMenu" role="menu">
                <button
                  className="wf2-navMenuItem"
                  type="button"
                  onClick={() =>
                    navigate("/movies", { state: { filter: "now", hideTabs: true } })
                  }
                >
                  NOW SHOWING
                </button>
                <button
                  className="wf2-navMenuItem"
                  type="button"
                  onClick={() =>
                    navigate("/movies", { state: { filter: "soon", hideTabs: true } })
                  }
                >
                  COMING SOON
                </button>
              </div>
            </div>
            <button
              className={`wf2-pillTop ${isActive(path, "/schedules") ? "wf2-pillTopActive" : ""}`}
              onClick={() => navigate("/schedules")}
            >
              SCHEDULES
            </button>
            <button
              className={`wf2-pillTop ${isActive(path, "/cinemas") ? "wf2-pillTopActive" : ""}`}
              onClick={() => navigate("/cinemas")}
            >
              CINEMAS
            </button>
          </nav>
        </div>

        {!user ? (
          <button
            className="wf2-btn wf2-btnPrimary wf2-btnPill"
            onClick={() => navigate("/login")}
          >
            Sign in
          </button>
        ) : (
          <div className="wf2-userActions">
            <button
              className="wf2-noticeBell"
              type="button"
              onClick={() => setNotificationSidebarOpen(true)}
              aria-label="Notifications"
              title="Notifications"
            >
              <Bell size={18} />
              {unreadCount > 0 ? (
                <span className="wf2-noticeBadge">{unreadCount > 99 ? "99+" : unreadCount}</span>
              ) : null}
            </button>

            <div className="wf2-navItem wf2-navDropdown wf2-userDropdown">
              <button
                className="wf2-userBtn"
                type="button"
                onClick={() => navigate("/profile")}
                aria-label="Account menu"
                title={displayName || "Profile"}
              >
                <span className="wf2-userGreeting">
                  <span className="wf2-userHello">{getTimeGreeting()}</span>
                  <span className="wf2-userName">{username || "User"}</span>
                </span>
                <span className="wf2-userAvatar">
                  {avatarSrc ? (
                    <img src={avatarSrc} alt="Profile avatar" />
                  ) : initials ? (
                    <span className="wf2-userInitials">{initials}</span>
                  ) : (
                    <User size={16} />
                  )}
                </span>
                <ChevronDown size={18} />
              </button>
              <div className="wf2-navMenu wf2-userMenu" role="menu">
                <button
                  className="wf2-navMenuItem"
                  type="button"
                  onClick={() => navigate("/profile")}
                >
                  PROFILE
                </button>
                <button
                  className="wf2-navMenuItem"
                  type="button"
                  onClick={() => navigate("/bookings/history")}
                >
                  BOOKING HISTORY
                </button>
                <button
                  className="wf2-navMenuItem"
                  type="button"
                  onClick={() => navigate("/group-booking/new")}
                >
                  GROUP BOOKINGS
                </button>
                <button
                  className="wf2-navMenuItem"
                  type="button"
                  onClick={() => navigate("/loyalty/dashboard")}
                >
                  LOYALTY DASHBOARD
                </button>
                <button
                  className="wf2-navMenuItem"
                  type="button"
                  onClick={() => navigate("/subscriptions/dashboard")}
                >
                  MEMBERSHIP
                </button>
                <button
                  className="wf2-navMenuItem"
                  type="button"
                  onClick={() => navigate("/subscriptions/plans")}
                >
                  MEMBERSHIP PLANS
                </button>
                <button
                  className="wf2-navMenuItem"
                  type="button"
                  onClick={() => navigate("/loyalty/rewards")}
                >
                  REWARDS
                </button>
                <button
                  className="wf2-navMenuItem"
                  type="button"
                  onClick={() => navigate("/referral/wallet")}
                >
                  REFERRAL WALLET
                </button>
                <button
                  className="wf2-navMenuItem"
                  type="button"
                  onClick={() => navigate("/notifications")}
                >
                  NOTIFICATIONS
                </button>
                <button
                  className="wf2-navMenuItem"
                  type="button"
                  onClick={handleLogout}
                >
                  LOGOUT
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      <nav className="wf2-mobileNavTabs" aria-label="Mobile quick navigation">
        <button
          type="button"
          className={`wf2-mobileNavTab ${isActive(path, "/") ? "wf2-mobileNavTabActive" : ""}`}
          onClick={() => navigate("/")}
        >
          Home
        </button>
        <button
          type="button"
          className={`wf2-mobileNavTab ${path.startsWith("/movie") ? "wf2-mobileNavTabActive" : ""}`}
          onClick={() => navigate("/movies")}
        >
          Movies
        </button>
        <button
          type="button"
          className={`wf2-mobileNavTab ${isActive(path, "/schedules") ? "wf2-mobileNavTabActive" : ""}`}
          onClick={() => navigate("/schedules")}
        >
          Schedules
        </button>
        <button
          type="button"
          className={`wf2-mobileNavTab ${isActive(path, "/cinemas") ? "wf2-mobileNavTabActive" : ""}`}
          onClick={() => navigate("/cinemas")}
        >
          Cinemas
        </button>
      </nav>

      <AdultWarningModal
        open={adultConfirmOpen}
        onCancel={() => {
          setAdultConfirmOpen(false);
          setPendingBookingState(null);
        }}
        onConfirm={() => {
          const next = pendingBookingState;
          setAdultConfirmOpen(false);
          setPendingBookingState(null);
          navigateToBookingState(next);
        }}
      />

      <UserNotificationSidebar
        isOpen={notificationSidebarOpen}
        onClose={() => setNotificationSidebarOpen(false)}
      />

      {locationOpen ? (
        <div className="wf2-locationOverlay" onClick={() => setLocationOpen(false)}>
          <div className="wf2-locationModal" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className="wf2-locationClose"
              aria-label="Close"
              onClick={() => setLocationOpen(false)}
            >
              X
            </button>
            <div className="wf2-locationTitle">Cities</div>
            <div className="wf2-locationRule" />
            <div className="wf2-locationGrid">
              <button
                type="button"
                className={`wf2-locationCity ${!appSelectedLocation ? "wf2-locationCityActive" : ""}`}
                onClick={() => {
                  if (setAppSelectedLocation) {
                    setAppSelectedLocation("");
                  }
                  setLocationOpen(false);
                }}
              >
                All Cities
              </button>
              {locations.map((loc) => (
                <button
                  key={loc}
                  type="button"
                  className={`wf2-locationCity ${appSelectedLocation === loc ? "wf2-locationCityActive" : ""}`}
                  onClick={() => {
                    if (setAppSelectedLocation) {
                      setAppSelectedLocation(loc);
                    }
                    setLocationOpen(false);
                  }}
                >
                  {loc}
                </button>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      <div className="wf2-headerBottom">
        <div className="wf2-bookingBar" ref={bookingRef}>
          <div className="wf2-bookingLabel">
            <span className="wf2-ticketIcon" aria-hidden="true">
              <svg viewBox="0 0 24 24" role="presentation">
                <path
                  className="wf2-ticketStroke"
                  d="M4.5 7.5a1.5 1.5 0 0 1 1.5-1.5h12a1.5 1.5 0 0 1 1.5 1.5v2.25a2.25 2.25 0 0 0 0 4.5v2.25a1.5 1.5 0 0 1-1.5 1.5h-12a1.5 1.5 0 0 1-1.5-1.5v-2.25a2.25 2.25 0 0 0 0-4.5z"
                />
                <path
                  className="wf2-ticketStroke"
                  d="M10 8.25v7.5"
                />
                <path
                  className="wf2-ticketStroke"
                  d="M13.5 11.25l1.05 2.1 2.32.34-1.68 1.64.4 2.31-2.09-1.1-2.08 1.1.4-2.31-1.68-1.64 2.32-.34z"
                />
              </svg>
            </span>
            <div className="wf2-bookingToggle">
              <button
                type="button"
                className={`wf2-bookingTab ${bookingMode === "cinema" ? "wf2-bookingTabActive" : ""}`}
                onClick={() => setBookingMode("cinema")}
              >
                Cinema
              </button>
              <span className="wf2-bookingDivider">|</span>
              <button
                type="button"
                className={`wf2-bookingTab ${bookingMode === "movie" ? "wf2-bookingTabActive" : ""}`}
                onClick={() => setBookingMode("movie")}
              >
                Movie
              </button>
            </div>
          </div>
          <div className="wf2-bookingControls">
            {bookingMode === "cinema" ? (
              <>
                <SelectField
                  id="cinema"
                  label="Select Cinema"
                  value={selectedCinemaId}
                  options={cinemaOptions}
                  onChange={setSelectedCinemaId}
                  disabled={cinemaLocked}
                  placeholder="Select Cinema"
                />
                <SelectField
                  id="movie"
                  label="Select Movie"
                  value={selectedMovieId}
                  options={movieOptions}
                  onChange={setSelectedMovieId}
                  disabled={movieLocked}
                  placeholder="Select Movie"
                />
              </>
            ) : (
              <>
                <SelectField
                  id="movie"
                  label="Select Movie"
                  value={selectedMovieId}
                  options={movieOptions}
                  onChange={setSelectedMovieId}
                  disabled={movieLocked}
                  placeholder="Select Movie"
                />
                <SelectField
                  id="cinema"
                  label="Select Cinema"
                  value={selectedCinemaId}
                  options={cinemaOptions}
                  onChange={setSelectedCinemaId}
                  disabled={cinemaLocked}
                  placeholder="Select Cinema"
                />
              </>
            )}

            <SelectField
              id="date"
              label="Select Date"
              value={selectedDate}
              options={dateOptions}
              onChange={(value) => {
                setSelectedDate(value);
                setSelectedTime("");
              }}
              disabled={dateLocked}
              placeholder="Select Date"
            />

            <SelectField
              id="time"
              label="Select Time"
              value={selectedTime}
              options={timeOptions}
              onChange={setSelectedTime}
              disabled={timeLocked}
              placeholder="Select Time"
            />

            <button
              className="wf2-buyNowBtn"
              type="button"
              disabled={!isBookingReady}
              onClick={handleBuyNow}
            >
              Buy Now
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}

function safeUseAppContext() {
  try {
    return useAppContext?.();
  } catch {
    return null;
  }
}

function coerceNumber(value) {
  const parsed = Number(value);
  return Number.isInteger(parsed) ? parsed : null;
}

function findMatchingShowId(showtimes, cinemaId, movieId, dateValue, timeValue) {
  const targetCinema = coerceNumber(cinemaId);
  const targetMovie = coerceNumber(movieId);
  const targetDate = normalizeIsoDate(dateValue);
  const targetTime = normalizeClockTime(timeValue);
  if (!targetCinema || !targetMovie || !targetDate || !targetTime) return null;

  const list = Array.isArray(showtimes) ? showtimes : [];
  const matched = list.find((show) => {
    const showCinema = coerceNumber(show?.vendor_id || show?.vendorId || show?.vendor);
    const showMovie = coerceNumber(show?.movie_id || show?.movieId || show?.movie);
    const showDate = normalizeIsoDate(show?.show_date || show?.date || show?.showDate);
    const showTime = normalizeClockTime(show?.start_time || show?.start || show?.startTime);

    return (
      showCinema === targetCinema &&
      showMovie === targetMovie &&
      showDate === targetDate &&
      showTime === targetTime
    );
  });

  return coerceNumber(matched?.id || matched?.show_id || matched?.showId);
}

function normalizeIsoDate(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (iso) return `${iso[1]}-${iso[2]}-${iso[3]}`;

  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return "";
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function normalizeClockTime(value) {
  const text = String(value || "").trim().toUpperCase();
  if (!text) return "";

  const hour24 = text.match(/^(\d{1,2}):(\d{2})(?::\d{2})?$/);
  if (hour24) {
    const hour = Number(hour24[1]);
    const minute = Number(hour24[2]);
    if (Number.isNaN(hour) || Number.isNaN(minute)) return "";
    return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
  }

  const ampm = text.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/);
  if (!ampm) return "";
  let hour = Number(ampm[1]) % 12;
  const minute = Number(ampm[2]);
  if (Number.isNaN(hour) || Number.isNaN(minute)) return "";
  if (ampm[3] === "PM") hour += 12;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function isActive(path, target) {
  if (target === "/") return path === "/" || path === "/home" || path === "/dashboard";
  return path.startsWith(target);
}

function getStoredUser() {
  return getStoredRoleData("customer");
}

function getUserDisplayName(user) {
  if (!user) return "";
  const parts = [user.first_name, user.middle_name, user.last_name].filter(Boolean);
  if (parts.length) return parts.join(" ");
  if (user.name) return user.name;
  if (user.username) return user.username;
  if (user.email) return user.email;
  if (user.phone_number) return user.phone_number;
  if (user.phone) return user.phone;
  return "";
}

function getUserUsername(user) {
  if (!user) return "";
  if (user.username) return user.username;
  if (user.email) return user.email.split("@")[0];
  if (user.phone_number) return user.phone_number;
  if (user.phone) return user.phone;
  return "";
}

function getUserInitials(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) return "";
  const parts = trimmed.split(/\s+/);
  if (parts.length === 1) {
    return parts[0].slice(0, 3).toUpperCase();
  }
  return parts
    .slice(0, 3)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function getTimeGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good Morning,";
  if (hour < 18) return "Good Afternoon,";
  return "Good Evening,";
}

function splitGenres(value) {
  return String(value || "")
    .split(/[|,/]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function getMoviePoster(movie) {
  return (
    movie?.posterImage ||
    movie?.poster_image ||
    movie?.poster ||
    movie?.posterUrl ||
    movie?.poster_url ||
    movie?.image ||
    movie?.thumbnail ||
    logo
  );
}

function getUserAvatar(user) {
  if (!user) return "";
  return (
    user.avatar ||
    user.avatarUrl ||
    user.profile_image ||
    user.profileImage ||
    user.photo ||
    user.image ||
    ""
  );
}
