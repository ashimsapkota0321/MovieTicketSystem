import React, { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import "../css/Login.css";
import HeroImage1 from "../images/gharjwai.jpg";
import HeroImage2 from "../images/balidan.jpg";
import HeroImage3 from "../images/degreemaila.jpg";
import HeroImage4 from "../images/avengers.jpg";
import Logo from "../images/logo.png";
import { useAppContext } from "../context/Appcontext";
import { buildAuthHeroSlides } from "../lib/authHeroSlides";
import {
  getStoredRoleData,
  storeAuthSession,
  storeRoleData,
} from "../lib/authSession";
import { API_BASE } from "../lib/apiBase";

const SUPER_ADMIN_EMAIL = "asimsapkota2005@gmail.com";
const SUPER_ADMIN_PHONE = "+977-9826633701";
const VENDOR_REGISTRATION_EMAIL = "asimsapkota2005@gmail.com";
const REQUIRED_FIELD_MESSAGES = {
  emailOrPhone: "Please enter your email, phone number, or username",
  password: "Please enter your password",
};

const LoginPage = () => {
  const navigate = useNavigate();
  const [emailOrPhone, setEmailOrPhone] = useState("");
  const [password, setPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [showTermsModal, setShowTermsModal] = useState(false);
  const ctx = safeUseAppContext();

  const handleAuthenticatedResponse = (data) => {
    setSuccess((data && data.message) || "Login successful!");
    setEmailOrPhone("");
    setPassword("");

    const isAdminLogin = data && (data.role === "admin" || data.admin);
    if (isAdminLogin) {
      const scope = rememberMe ? "local" : "session";
      storeAuthSession("admin", data?.access_token || "", { scope });
      if (data.admin) storeRoleData("admin", data.admin, { scope });
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("mt:admin-updated"));
      }
      setTimeout(() => {
        navigate("/admin", { replace: true });
      }, 1500);
      return true;
    }

    const isVendorLogin = data && (data.role === "vendor" || data.vendor);
    if (isVendorLogin) {
      const scope = rememberMe ? "local" : "session";
      const vendorPayload = {
        ...(data.vendor || {}),
        vendor_staff: data?.vendor_staff || null,
        staff: data?.vendor_staff || null,
        staff_role: String(data?.vendor_staff?.role || "").toUpperCase() || null,
        is_owner: !data?.vendor_staff,
      };
      storeAuthSession("vendor", data?.access_token || "", { scope });
      if (data.vendor) storeRoleData("vendor", vendorPayload, { scope });
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("mt:vendor-updated"));
      }
      setTimeout(() => {
        navigate("/vendor", { replace: true });
      }, 1500);
      return true;
    }

    if (data && data.user) {
      const existingGlobalUser = getStoredRoleData("customer", { scope: "local" });
      const existingKey = getAccountKey(existingGlobalUser);
      const nextKey = getAccountKey(data.user);
      const scopeByAccountIsolation =
        existingKey && nextKey && existingKey !== nextKey ? "session" : "local";
      const scope = rememberMe ? scopeByAccountIsolation : "session";

      storeAuthSession("customer", data?.access_token || "", { scope });
      storeRoleData("customer", data.user, { scope });
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("mt:user-updated"));
      }
      setTimeout(() => {
        navigate("/", { replace: true });
      }, 1500);
      return true;
    }

    return false;
  };

  const heroSlides = useMemo(() => {
    const dynamicSlides = buildAuthHeroSlides(ctx?.movies, ctx?.showtimes, {
      nowLimit: 5,
      soonLimit: 5,
      maxSlides: 8,
    });
    if (dynamicSlides.length) return dynamicSlides;

    return [
      {
        id: "fallback-now-1",
        badge: "Now Showing",
        title: "Book your next movie in seconds",
        description:
          "Discover the latest shows, compare vendors, and secure your seats with a single tap.",
        image: HeroImage1,
      },
      {
        id: "fallback-now-2",
        badge: "Now Showing",
        title: "Your favorite movies are one tap away",
        description:
          "Find shows near you, pick seats faster, and enjoy a smoother booking experience.",
        image: HeroImage2,
      },
      {
        id: "fallback-soon-1",
        badge: "Coming Soon",
        title: "Upcoming releases are almost here",
        description:
          "Sign in to stay ready for new releases and grab your seats as soon as they go live.",
        image: HeroImage3,
      },
      {
        id: "fallback-soon-2",
        badge: "Coming Soon",
        title: "Stay ready for the next big premiere",
        description:
          "Track upcoming movies and be first in line when bookings open.",
        image: HeroImage4,
      },
    ];
  }, [ctx?.movies, ctx?.showtimes]);

  const [currentSlide, setCurrentSlide] = useState(0);
  const activeSlide = heroSlides[currentSlide] || heroSlides[0] || null;

  // Auto-slide hero entries when more than one slide is available.
  useEffect(() => {
    if (heroSlides.length <= 1) return undefined;
    const interval = setInterval(() => {
      setCurrentSlide((prev) => (prev + 1) % heroSlides.length);
    }, 4000); // 4 seconds

    return () => clearInterval(interval);
  }, [heroSlides.length]);

  useEffect(() => {
    setCurrentSlide((prev) => {
      if (!heroSlides.length) return 0;
      return prev >= heroSlides.length ? 0 : prev;
    });
  }, [heroSlides.length]);

  const validateEmail = (email) =>
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

  const validatePhone = (phone) =>
    /^\+?[0-9]{10,13}$/.test(phone);

  const validateUsername = (value) =>
    /^[a-zA-Z0-9._-]{3,}$/.test(value);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    const nextFieldErrors = {};

    if (!String(emailOrPhone || "").trim()) {
      nextFieldErrors.emailOrPhone = REQUIRED_FIELD_MESSAGES.emailOrPhone;
    }

    if (!String(password || "").trim()) {
      nextFieldErrors.password = REQUIRED_FIELD_MESSAGES.password;
    }

    if (!nextFieldErrors.emailOrPhone && emailOrPhone.includes("@")) {
      if (!validateEmail(emailOrPhone)) {
        nextFieldErrors.emailOrPhone = "Invalid email format";
      }
    } else if (!nextFieldErrors.emailOrPhone && !validatePhone(emailOrPhone) && !validateUsername(emailOrPhone)) {
      nextFieldErrors.emailOrPhone = "Enter a valid email, phone number, or username";
    }

    setFieldErrors(nextFieldErrors);
    if (Object.keys(nextFieldErrors).length > 0) {
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/auth/login/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          email_or_phone: emailOrPhone,
          password: password,
        }),
      });

      let data = null;
      try {
        data = await response.json();
      } catch (parseErr) {
        console.error("Failed to parse JSON:", parseErr);
      }

      if (!response.ok) {
        const errorMessage =
          (data && (data.message || data.error)) ||
          `Server error: ${response.status}`;
        throw new Error(errorMessage);
      }

      handleAuthenticatedResponse(data);
    } catch (err) {
      console.error("Login error:", err);
      setError(err.message || "An unexpected error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-login-root">
      <div className="mt-login-card">
        {/* LEFT SIDE - FORM */}
        <div className="mt-login-left">
          <img
            src={Logo}
            alt="Mero Ticket Logo"
            className="mt-logo"
          />
          <button
            type="button"
            className="mt-terms-launch-btn"
            aria-label="Open terms and conditions"
            onClick={() => setShowTermsModal(true)}
          >
            <span className="mt-terms-launch-icon" aria-hidden="true">
              i
            </span>
          </button>

          <h2 className="mt-title">Welcome to Mero Ticket</h2>
          <p className="mt-subtitle">
            Please enter your details to login
          </p>

          <form className="mt-form" onSubmit={handleSubmit} noValidate>
            {/* Email / Phone */}
            <label className="mt-label">
              Email or Phone Number
              <div className={`mt-input-wrapper ${fieldErrors.emailOrPhone ? "mt-input-invalid" : ""}`}>
                <span className="mt-icon material-symbols-outlined">
                  person
                </span>
                <input
                  type="text"
                  placeholder="Enter your Email or Phone Number"
                  value={emailOrPhone}
                  onChange={(e) => {
                    setEmailOrPhone(e.target.value);
                    setError("");
                    setFieldErrors((prev) => {
                      if (!prev.emailOrPhone) return prev;
                      const next = { ...prev };
                      delete next.emailOrPhone;
                      return next;
                    });
                  }}
                  disabled={loading}
                  required
                />
              </div>
              {fieldErrors.emailOrPhone ? <div className="mt-field-error">{fieldErrors.emailOrPhone}</div> : null}
            </label>

            {/* Password */}
            <label className="mt-label">
              Password
              <div className={`mt-input-wrapper ${fieldErrors.password ? "mt-input-invalid" : ""}`}>
                <span className="mt-icon material-symbols-outlined">
                  lock
                </span>
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setError("");
                    setFieldErrors((prev) => {
                      if (!prev.password) return prev;
                      const next = { ...prev };
                      delete next.password;
                      return next;
                    });
                  }}
                  disabled={loading}
                  required
                  minLength={8}
                />
                <button
                  type="button"
                  className="mt-eye-btn"
                  tabIndex={-1}
                  onClick={() => setShowPassword(!showPassword)}
                >
                  <span className="material-symbols-outlined">
                    {showPassword ? "visibility_off" : "visibility"}
                  </span>
                </button>
              </div>
              {fieldErrors.password ? <div className="mt-field-error">{fieldErrors.password}</div> : null}
            </label>

            {/* Remember + Forgot */}
            <div className="mt-row-between mt-small-row">
              <label className="mt-remember">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(event) => setRememberMe(event.target.checked)}
                  disabled={loading}
                />
                <span>Remember me</span>
              </label>

              <button
                type="button"
                className="mt-link-btn"
                disabled={loading}
                onClick={() => navigate("/forgot-password")}
              >
                Forget Password?
              </button>
            </div>

            {/* Error / Success */}
            {error && <div className="mt-error">{error}</div>}
            {success && <div className="mt-success">{success}</div>}

            {/* Submit */}
            <button
              type="submit"
              className="mt-primary-btn"
              disabled={loading}
            >
              {loading ? "Signing in..." : "Sign in"}
            </button>

            {/* Footer */}
            <div className="mt-footer-text">
              Don&apos;t have an account?{" "}
              <button
                type="button"
                className="mt-cta"
                onClick={() => navigate("/register")}
                disabled={loading}
              >
                Create an account
              </button>
            </div>
          </form>
        </div>

        {/* RIGHT SIDE - HERO SLIDER */}
        <div
          className="mt-login-right"
          style={{
            backgroundImage: activeSlide?.image ? `url(${activeSlide.image})` : "none",
          }}
        >
          <div className="mt-hero-card-overlay">
            <div className="mt-hero-badge">{activeSlide?.badge || "Now Showing"}</div>
            <h2>{activeSlide?.title || "Book your next movie in seconds"}</h2>
            <p>
              {activeSlide?.description ||
                "Discover the latest shows, compare vendors, and secure your seats with a single tap."}
            </p>

            <div className="mt-carousel-dots">
              {heroSlides.map((slide, index) => (
                <span
                  key={slide.id || index}
                  className={`dot ${
                    index === currentSlide ? "active" : ""
                  }`}
                  onClick={() => setCurrentSlide(index)}
                ></span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {showTermsModal ? (
        <div
          className="mt-terms-modal-backdrop"
          onClick={() => setShowTermsModal(false)}
          role="presentation"
        >
          <div
            className="mt-terms-modal"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Terms and Conditions"
          >
            <button
              type="button"
              className="mt-terms-modal-close"
              onClick={() => setShowTermsModal(false)}
            >
              Close
            </button>

            <h3 className="mt-terms-modal-title">Terms & Conditions</h3>
            <p className="mt-terms-modal-text">
              By signing in, you agree to Mero Ticket terms and policies.
            </p>
            <p className="mt-terms-modal-text">
              Vendor registration is handled manually by super admin.
              Please email{" "}
              <a href={`mailto:${VENDOR_REGISTRATION_EMAIL}`}>{VENDOR_REGISTRATION_EMAIL}</a>.
            </p>
            <p className="mt-terms-modal-text">
              Super admin contact:{" "}
              <a href={`mailto:${SUPER_ADMIN_EMAIL}`}>{SUPER_ADMIN_EMAIL}</a>{" "}
              |{" "}
              <a href={`tel:${SUPER_ADMIN_PHONE.replace(/[^+\d]/g, "")}`}>
                {SUPER_ADMIN_PHONE}
              </a>
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default LoginPage;

function safeUseAppContext() {
  try {
    return useAppContext?.();
  } catch {
    return null;
  }
}

function getAccountKey(user) {
  if (!user) return "";
  const key =
    user.id ||
    user._id ||
    user.user_id ||
    user.email ||
    user.username ||
    user.phone_number ||
    user.phone;
  return String(key || "").trim().toLowerCase();
}
