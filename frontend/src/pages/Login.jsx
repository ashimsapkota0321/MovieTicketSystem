import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import "../css/Login.css";
import HeroImage1 from "../images/gharjwai.jpg";
import HeroImage2 from "../images/balidan.jpg";
import HeroImage3 from "../images/degreemaila.jpg";
import HeroImage4 from "../images/avengers.jpg";
import Logo from "../images/logo.png";
import {
  getStoredRoleData,
  storeAuthSession,
  storeRoleData,
} from "../lib/authSession";

const API_BASE =
  import.meta.env.VITE_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

const LoginPage = () => {
  const navigate = useNavigate();
  const [emailOrPhone, setEmailOrPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);

  // hero images array
  const heroImages = [HeroImage1, HeroImage2, HeroImage3,HeroImage4];
  const [currentSlide, setCurrentSlide] = useState(0);

  // auto-slide with infinite loop
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentSlide((prev) => (prev + 1) % heroImages.length);
    }, 4000); // 4 seconds

    return () => clearInterval(interval);
  }, [heroImages.length]);

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

    if (!emailOrPhone || !password) {
      setError("All fields are required");
      return;
    }

    if (emailOrPhone.includes("@")) {
      if (!validateEmail(emailOrPhone)) {
        setError("Invalid email format");
        return;
      }
    } else if (!validatePhone(emailOrPhone) && !validateUsername(emailOrPhone)) {
      setError("Enter a valid email, phone number, or username");
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
        return;
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
        return;
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
      }
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

          <h2 className="mt-title">Welcome to Mero Ticket</h2>
          <p className="mt-subtitle">
            Please enter your details to login
          </p>

          <form className="mt-form" onSubmit={handleSubmit}>
            {/* Email / Phone */}
            <label className="mt-label">
              Email or Phone Number
              <div className="mt-input-wrapper">
                <span className="mt-icon material-symbols-outlined">
                  person
                </span>
                <input
                  type="text"
                  placeholder="Enter your Email or Phone Number"
                  value={emailOrPhone}
                  onChange={(e) => setEmailOrPhone(e.target.value)}
                  disabled={loading}
                  required
                />
              </div>
            </label>

            {/* Password */}
            <label className="mt-label">
              Password
              <div className="mt-input-wrapper">
                <span className="mt-icon material-symbols-outlined">
                  lock
                </span>
                <input
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
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
            backgroundImage: `url(${heroImages[currentSlide]})`,
          }}
        >
          <div className="mt-hero-card-overlay">
            <div className="mt-hero-badge">Now Showing</div>
            <h2>Book your next movie in seconds</h2>
            <p>
              Discover the latest shows, compare vendors, and secure your
              seats with a single tap.
            </p>

            <div className="mt-carousel-dots">
              {heroImages.map((_, index) => (
                <span
                  key={index}
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
    </div>
  );
};

export default LoginPage;

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
