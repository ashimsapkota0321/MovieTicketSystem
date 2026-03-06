import React, { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ChevronDown, Search, User } from "lucide-react";
import { useAppContext } from "../context/Appcontext";
import api from "../api/api";
import { clearAuthSession } from "../lib/authSession";
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
  const bookingRef = useRef(null);

  const [scrolled, setScrolled] = useState(false);
  const [selectedLocation, setSelectedLocation] = useState("Pokhara");
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
  const [searchTerm, setSearchTerm] = useState("");
  const [storedUser, setStoredUser] = useState(() => getStoredUser());
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

  const locations = [
    "Kathmandu",
    "Butwal",
    "Nepalgunj",
    "Narayangarh",
    "Birtamode",
    "Damauli",
    "Itahari",
    "Birgunj",
    "Pokhara",
  ];
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

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (bookingRef.current && !bookingRef.current.contains(event.target)) {
        setOpenSelect(null);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

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
          api.get("/api/booking/cinemas/"),
          api.get("/api/booking/movies/"),
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
  }, []);

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
          params: { cinema_id: selectedCinemaId },
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
  }, [selectedCinemaId, bookingMode]);

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
          params: { movie_id: selectedMovieId },
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
  }, [selectedMovieId, bookingMode]);

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
  }, [selectedCinemaId, selectedMovieId]);

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
  }, [selectedCinemaId, selectedMovieId, selectedDate]);

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

  const ctx = safeUseAppContext();
  const user = ctx?.user ?? storedUser;
  const displayName = getUserDisplayName(user);
  const username = getUserUsername(user);
  const initials = getUserInitials(displayName || username);
  const avatarSrc = getUserAvatar(user);

  const handleLogout = () => {
    clearAuthSession();
    localStorage.removeItem("user");
    setStoredUser(null);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("mt:user-updated"));
    }
    navigate("/login");
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
    <header className={`wf2-header ${scrolled ? "wf2-headerScrolled" : ""}`}>
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
              <span>{selectedLocation}</span>
              <ChevronDown size={18} />
            </button>
          </div>
        </div>

        <div className="wf2-headerNav">
          <div className="wf2-search" role="search">
            <Search size={18} />
            <input
              type="text"
              placeholder="Movie, Title, Genre..."
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              aria-label="Search movies"
            />
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
                onClick={handleLogout}
              >
                LOGOUT
              </button>
            </div>
          </div>
        )}
      </div>

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
              {locations.map((loc) => (
                <button
                  key={loc}
                  type="button"
                  className={`wf2-locationCity ${selectedLocation === loc ? "wf2-locationCityActive" : ""}`}
                  onClick={() => {
                    setSelectedLocation(loc);
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
              onClick={() => {
                if (!isBookingReady) return;
                navigate("/booking", {
                  state: {
                    movie: {
                      id: coerceNumber(selectedMovieId),
                      title: selectedMovieOption?.label || "Movie",
                    },
                    vendor: {
                      id: coerceNumber(selectedCinemaId),
                      name: selectedCinemaOption?.label || "Cinema",
                    },
                    date: selectedDate,
                    time: selectedTime,
                  },
                });
              }}
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

function isActive(path, target) {
  if (target === "/") return path === "/" || path === "/home" || path === "/dashboard";
  return path.startsWith(target);
}

function getStoredUser() {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("user");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
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
