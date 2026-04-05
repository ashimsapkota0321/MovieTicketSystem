import React, { useState, useEffect } from "react";
import "../css/Login.css";
import HeroImage1 from "../images/gharjwai.jpg";
import HeroImage2 from "../images/balidan.jpg";
import HeroImage3 from "../images/degreemaila.jpg";
import HeroImage4 from "../images/avengers.jpg";
import Logo from "../images/logo.png";
import { API_BASE } from "../lib/apiBase";

const ForgotPasswordPage = () => {
  const [step, setStep] = useState(1); // 1: email, 2: otp, 3: password
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [otpTimer, setOtpTimer] = useState(0);
  const [resendTimer, setResendTimer] = useState(0);

  // hero images array
  const heroImages = [HeroImage1, HeroImage2, HeroImage3, HeroImage4];
  const [currentSlide, setCurrentSlide] = useState(0);

  // auto-slide with infinite loop
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentSlide((prev) => (prev + 1) % heroImages.length);
    }, 4000); // 4 seconds

    return () => clearInterval(interval);
  }, [heroImages.length]);

  // OTP timer countdown
  useEffect(() => {
    if (otpTimer > 0) {
      const timer = setTimeout(() => setOtpTimer(otpTimer - 1), 1000);
      return () => clearTimeout(timer);
    }
  }, [otpTimer]);

  useEffect(() => {
    if (resendTimer > 0) {
      const rTimer = setTimeout(() => setResendTimer(resendTimer - 1), 1000);
      return () => clearTimeout(rTimer);
    }
  }, [resendTimer]);

  const validateEmail = (email) =>
    /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

  const handleRequestOtp = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (!email) {
      setError("Email is required");
      return;
    }

    if (!validateEmail(email)) {
      setError("Invalid email format");
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(
        `${API_BASE}/api/auth/forgot-password/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({ email }),
        }
      );

      const text = await response.text();
      let data = {};
      try {
        data = JSON.parse(text);
      } catch {
        data = { error: text };
      }

      if (!response.ok) {
        const message = data?.message || data?.error || `Server error: ${response.status}`;
        throw new Error(message || "Failed to send OTP");
      }

      setSuccess(data?.message || "OTP sent to your email");
      setStep(2);
      setOtpTimer(240);
      setResendTimer(60);
    } catch (err) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  const handleResendOtp = async () => {
    if (resendTimer > 0 || loading) return;
    // call the same request handler without a DOM event
    await handleRequestOtp({ preventDefault: () => {} });
  };

  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (!otp) {
      setError("OTP is required");
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(
        `${API_BASE}/api/auth/verify-otp/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({ email, otp }),
        }
      );

      const text = await response.text();
      let data = {};
      try {
        data = JSON.parse(text);
      } catch {
        data = { error: text };
      }

      if (!response.ok) {
        const message = data?.message || data?.error || `Server error: ${response.status}`;
        throw new Error(message || "Invalid OTP");
      }

      setSuccess("OTP verified successfully");
      setStep(3);
      setOtpTimer(0);
    } catch (err) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (!newPassword || !confirmPassword) {
      setError("All fields are required");
      return;
    }

    if (newPassword !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(
        `${API_BASE}/api/auth/reset-password/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({
            email,
            otp,
            new_password: newPassword,
          }),
        }
      );

      const text = await response.text();
      let data = {};
      try {
        data = JSON.parse(text);
      } catch {
        data = { error: text };
      }

      if (!response.ok) {
        const message = data?.message || data?.error || `Server error: ${response.status}`;
        throw new Error(message || "Failed to reset password");
      }

      setSuccess("Password reset successful! Redirecting to login...");
      setEmail("");
      setOtp("");
      setNewPassword("");
      setConfirmPassword("");

      setTimeout(() => {
        window.location.href = "/login";
      }, 1500);
    } catch (err) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-login-root">
      <div className="mt-login-card">
        {/* LEFT SIDE - FORM */}
        <div className="mt-login-left">
          <img src={Logo} alt="Mero Ticket Logo" className="mt-logo" />

          <h2 className="mt-title">Reset Password</h2>
          <p className="mt-subtitle">
            {step === 1 && "Enter your email to receive an OTP"}
            {step === 2 && "Enter the OTP sent to your email"}
            {step === 3 && "Create your new password"}
          </p>

          {step === 1 && (
            <form className="mt-form" onSubmit={handleRequestOtp}>
              <label className="mt-label">
                Email Address *
                <div className="mt-input-wrapper">
                  <span className="mt-icon material-symbols-outlined">
                    email
                  </span>
                  <input
                    type="email"
                    placeholder="Enter your email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    disabled={loading}
                    required
                  />
                </div>
              </label>

              {error && <div className="mt-error">{error}</div>}
              {success && <div className="mt-success">{success}</div>}

              <button
                type="submit"
                className="mt-primary-btn"
                disabled={loading}
              >
                {loading ? "Sending OTP..." : "Send OTP"}
              </button>

              <div className="mt-footer-text">
                Remember your password?{" "}
                <button
                  type="button"
                  className="mt-cta"
                  onClick={() => (window.location.href = "/login")}
                  disabled={loading}
                >
                  Sign In
                </button>
              </div>
            </form>
          )}

          {/* STEP 2: OTP */}
          {step === 2 && (
            <form className="mt-form" onSubmit={handleVerifyOtp}>
              <label className="mt-label">
                Enter OTP *
                <div className="mt-input-wrapper">
                  <span className="mt-icon material-symbols-outlined">
                    lock
                  </span>
                  <input
                    type="text"
                    placeholder="Enter 6-digit OTP"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value.slice(0, 6))}
                    disabled={loading}
                    maxLength="6"
                    required
                  />
                </div>
              </label>

              {resendTimer > 0 ? (
                <p className="mt-otp-resend">Resend available in: {resendTimer}s</p>
              ) : (
                <div className="mt-footer-text">
                  <button
                    type="button"
                    className="mt-link-btn"
                    onClick={handleResendOtp}
                    disabled={loading}
                  >
                    Resend OTP
                  </button>
                </div>
              )}

              {error && <div className="mt-error">{error}</div>}
              {success && <div className="mt-success">{success}</div>}

              <button
                type="submit"
                className="mt-primary-btn"
                disabled={loading}
              >
                {loading ? "Verifying..." : "Verify OTP"}
              </button>

              <div className="mt-footer-text">
                <button
                  type="button"
                  className="mt-link-btn"
                  onClick={() => {
                    setStep(1);
                    setOtp("");
                    setError("");
                    setSuccess("");
                  }}
                  disabled={loading}
                >
                  Back to Email
                </button>
              </div>
            </form>
          )}

          {/* STEP 3: NEW PASSWORD */}
          {step === 3 && (
            <form className="mt-form" onSubmit={handleResetPassword}>
              <label className="mt-label">
                New Password *
                <div className="mt-input-wrapper">
                  <span className="mt-icon material-symbols-outlined">
                    key
                  </span>
                  <input
                    type={showPassword ? "text" : "password"}
                    placeholder="Enter new password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
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

              <label className="mt-label">
                Confirm Password *
                <div className="mt-input-wrapper">
                  <span className="mt-icon material-symbols-outlined">
                    key
                  </span>
                  <input
                    type={showPassword ? "text" : "password"}
                    placeholder="Confirm new password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    disabled={loading}
                    required
                    minLength={8}
                  />
                </div>
              </label>

              {error && <div className="mt-error">{error}</div>}
              {success && <div className="mt-success">{success}</div>}

              <button
                type="submit"
                className="mt-primary-btn"
                disabled={loading}
              >
                {loading ? "Resetting..." : "Reset Password"}
              </button>

              <div className="mt-footer-text">
                <button
                  type="button"
                  className="mt-link-btn"
                  onClick={() => (window.location.href = "/login")}
                  disabled={loading}
                >
                  Back to Login
                </button>
              </div>
            </form>
          )}
        </div>

        {/* RIGHT SIDE - HERO SLIDER */}
        <div
          className="mt-login-right"
          style={{
            backgroundImage: `url(${heroImages[currentSlide]})`,
          }}
        >
          <div className="mt-hero-card-overlay">
            <div className="mt-hero-badge">Secure Access</div>
            <h2>Reset Your Password Safely</h2>
            <p>
              We'll verify your identity with an OTP and help you create a new
              password to protect your account.
            </p>

            <div className="mt-carousel-dots">
              {heroImages.map((_, index) => (
                <span
                  key={index}
                  className={`dot ${index === currentSlide ? "active" : ""}`}
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

export default ForgotPasswordPage;
