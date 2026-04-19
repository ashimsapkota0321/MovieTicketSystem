import React, { useState, useEffect } from "react";
import "../css/Login.css";
import HeroImage1 from "../images/gharjwai.jpg";
import HeroImage2 from "../images/balidan.jpg";
import HeroImage3 from "../images/degreemaila.jpg";
import HeroImage4 from "../images/avengers.jpg";
import Logo from "../images/logo.png";
import { API_BASE } from "../lib/apiBase";

const REQUIRED_FIELD_MESSAGES = {
  email: "Please enter your email",
  otp: "Please enter the OTP",
  newPassword: "Please enter your new password",
  confirmPassword: "Please confirm your new password",
};

const ForgotPasswordPage = () => {
  const [step, setStep] = useState(1); // 1: email, 2: otp, 3: password
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState({});
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [otpStatusNote, setOtpStatusNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [otpTimer, setOtpTimer] = useState(0);
  const [resendTimer, setResendTimer] = useState(0);
  const [resendCount, setResendCount] = useState(0);

  // hero images array
  const heroImages = [HeroImage1, HeroImage2, HeroImage3, HeroImage4];
  const [currentSlide, setCurrentSlide] = useState(0);
  const passwordRequirements = getPasswordRequirements(newPassword);
  const passwordMeetsRequirements = passwordRequirements.every((requirement) => requirement.valid);

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
    setOtpStatusNote("");

    if (!String(email || "").trim()) {
      setFieldErrors({ email: REQUIRED_FIELD_MESSAGES.email });
      return;
    }

    if (!validateEmail(String(email || "").trim())) {
      setFieldErrors({ email: "Invalid email format" });
      return;
    }
    setFieldErrors({});

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

      setSuccess(`OTP request complete for ${maskEmail(email)}.`);
      setOtpStatusNote(data?.message || "OTP sent to your email");
      setStep(2);
      setFieldErrors({});
      setOtpTimer(240);
      setResendTimer(60);
    } catch (err) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  const handleResendOtp = async () => {
    if (loading) return;
    setError("");
    setSuccess("");
    setOtpStatusNote("");
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
        throw new Error(message || "Failed to resend OTP");
      }

      const nowLabel = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      });
      setResendCount((prev) => prev + 1);
      setSuccess(`New OTP sent at ${nowLabel} for ${maskEmail(email)}.`);
      setOtpStatusNote(data?.message || "OTP sent to your email");
      setOtpTimer(240);
      setResendTimer(60);
    } catch (err) {
      setError(err.message || "An error occurred while resending OTP");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");
    setOtpStatusNote("");

    if (!String(otp || "").trim()) {
      setFieldErrors({ otp: REQUIRED_FIELD_MESSAGES.otp });
      return;
    }
    setFieldErrors({});

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
      setOtpStatusNote("You can now reset your password.");
      setStep(3);
      setFieldErrors({});
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
    const nextFieldErrors = {};

    if (!String(newPassword || "").trim()) {
      nextFieldErrors.newPassword = REQUIRED_FIELD_MESSAGES.newPassword;
    }

    if (!String(confirmPassword || "").trim()) {
      nextFieldErrors.confirmPassword = REQUIRED_FIELD_MESSAGES.confirmPassword;
    }

    if (!nextFieldErrors.newPassword && !passwordMeetsRequirements) {
      nextFieldErrors.newPassword = "Please meet all password requirements below";
    }

    if (!nextFieldErrors.confirmPassword && newPassword !== confirmPassword) {
      nextFieldErrors.confirmPassword = "Passwords do not match";
    }

    setFieldErrors(nextFieldErrors);
    if (Object.keys(nextFieldErrors).length > 0) {
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
      setFieldErrors({});

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
            <form className="mt-form" onSubmit={handleRequestOtp} noValidate>
              <label className="mt-label">
                Email Address *
                <div className={`mt-input-wrapper ${fieldErrors.email ? "mt-input-invalid" : ""}`}>
                  <span className="mt-icon material-symbols-outlined">
                    email
                  </span>
                  <input
                    type="email"
                    placeholder="Enter your email"
                    value={email}
                    onChange={(e) => {
                      setEmail(e.target.value);
                      setError("");
                      setFieldErrors((prev) => {
                        if (!prev.email) return prev;
                        const next = { ...prev };
                        delete next.email;
                        return next;
                      });
                    }}
                    disabled={loading}
                    required
                  />
                </div>
                {fieldErrors.email ? <div className="mt-field-error">{fieldErrors.email}</div> : null}
              </label>

              {error && <div className="mt-error">{error}</div>}
              {success && <div className="mt-success">{success}</div>}
              {otpStatusNote && <div className="mt-otp-note">{otpStatusNote}</div>}

              <button type="submit" className="mt-primary-btn" disabled={loading}>
                {loading ? "Generating and sending OTP..." : "Generate & Send OTP"}
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
            <form className="mt-form" onSubmit={handleVerifyOtp} noValidate>
              <label className="mt-label">
                Enter OTP *
                <div className={`mt-input-wrapper ${fieldErrors.otp ? "mt-input-invalid" : ""}`}>
                  <span className="mt-icon material-symbols-outlined">
                    lock
                  </span>
                  <input
                    type="text"
                    placeholder="Enter 6-digit OTP"
                    value={otp}
                    onChange={(e) => {
                      setOtp(e.target.value.slice(0, 6));
                      setError("");
                      setFieldErrors((prev) => {
                        if (!prev.otp) return prev;
                        const next = { ...prev };
                        delete next.otp;
                        return next;
                      });
                    }}
                    disabled={loading}
                    maxLength="6"
                    required
                  />
                </div>
                {fieldErrors.otp ? <div className="mt-field-error">{fieldErrors.otp}</div> : null}
              </label>

              <div className="mt-footer-text">
                <button type="button" className="mt-link-btn" onClick={handleResendOtp} disabled={loading}>
                  Send New OTP
                </button>
              </div>

              {resendTimer > 0 && (
                <p className="mt-otp-resend">You can resend again in: {resendTimer}s</p>
              )}

              {resendCount > 0 && (
                <p className="mt-otp-resend">Resent {resendCount} time{resendCount > 1 ? "s" : ""}.</p>
              )}

              {error && <div className="mt-error">{error}</div>}
              {success && <div className="mt-success">{success}</div>}
              {otpStatusNote && <div className="mt-otp-note">{otpStatusNote}</div>}

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
                    setFieldErrors({});
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
            <form className="mt-form" onSubmit={handleResetPassword} noValidate>
              <label className="mt-label">
                New Password *
                <div className={`mt-input-wrapper ${fieldErrors.newPassword ? "mt-input-invalid" : ""}`}>
                  <span className="mt-icon material-symbols-outlined">
                    key
                  </span>
                  <input
                    type={showPassword ? "text" : "password"}
                    placeholder="Enter new password"
                    value={newPassword}
                    onChange={(e) => {
                      setNewPassword(e.target.value);
                      setError("");
                      setFieldErrors((prev) => {
                        if (!prev.newPassword && !prev.confirmPassword) return prev;
                        const next = { ...prev };
                        delete next.newPassword;
                        delete next.confirmPassword;
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
                {fieldErrors.newPassword ? (
                  <div className="mt-field-error">{fieldErrors.newPassword}</div>
                ) : null}
                <div className="mt-password-guidance" aria-live="polite">
                  {passwordRequirements.map((requirement) => (
                    <div
                      key={requirement.key}
                      className={`mt-password-requirement ${requirement.valid ? "is-valid" : ""}`}
                    >
                      <span className="material-symbols-outlined" aria-hidden="true">
                        {requirement.valid ? "check_circle" : "radio_button_unchecked"}
                      </span>
                      <span>{requirement.label}</span>
                    </div>
                  ))}
                </div>
              </label>

              <label className="mt-label">
                Confirm Password *
                <div className={`mt-input-wrapper ${fieldErrors.confirmPassword ? "mt-input-invalid" : ""}`}>
                  <span className="mt-icon material-symbols-outlined">
                    key
                  </span>
                  <input
                    type={showPassword ? "text" : "password"}
                    placeholder="Confirm new password"
                    value={confirmPassword}
                    onChange={(e) => {
                      setConfirmPassword(e.target.value);
                      setError("");
                      setFieldErrors((prev) => {
                        if (!prev.confirmPassword) return prev;
                        const next = { ...prev };
                        delete next.confirmPassword;
                        return next;
                      });
                    }}
                    disabled={loading}
                    required
                    minLength={8}
                  />
                </div>
                {fieldErrors.confirmPassword ? (
                  <div className="mt-field-error">{fieldErrors.confirmPassword}</div>
                ) : null}
              </label>

              {error && <div className="mt-error">{error}</div>}
              {success && <div className="mt-success">{success}</div>}
              {otpStatusNote && <div className="mt-otp-note">{otpStatusNote}</div>}

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

function getPasswordRequirements(password) {
  const value = String(password || "");
  return [
    { key: "length", label: "At least 8 characters", valid: value.length >= 8 },
    { key: "letter", label: "1 letter", valid: /[A-Za-z]/.test(value) },
    { key: "number", label: "1 number", valid: /\d/.test(value) },
  ];
}

function maskEmail(value) {
  const email = String(value || "").trim();
  const atIndex = email.indexOf("@");
  if (atIndex <= 1) return email;

  const localPart = email.slice(0, atIndex);
  const domainPart = email.slice(atIndex);
  const visiblePrefix = localPart.slice(0, 2);
  const maskedMiddle = "*".repeat(Math.max(localPart.length - 2, 3));
  return `${visiblePrefix}${maskedMiddle}${domainPart}`;
}
