import React, { useState, useEffect } from "react";
import "../css/register.css";
import HeroImage1 from "../images/gharjwai.jpg";
import HeroImage2 from "../images/balidan.jpg";
import HeroImage3 from "../images/degreemaila.jpg";
import HeroImage4 from "../images/avengers.jpg";
import Logo from "../images/logo.png";

const RegisterPage = () => {
  const [formData, setFormData] = useState({
    first_name: "",
    middle_name: "",
    last_name: "",
    email: "",
    phone_number: "",
    dob: "",
    password: "",
    confirm_password: "",
  });

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  // Hero Slider Logic
  const heroImages = [HeroImage1, HeroImage2, HeroImage3, HeroImage4];
  const [currentSlide, setCurrentSlide] = useState(0);

  useEffect(() => {
    const interval = setInterval(
      () => setCurrentSlide((prev) => (prev + 1) % heroImages.length),
      4000
    );
    return () => clearInterval(interval);
  }, [heroImages.length]);

  const handleChange = (e) => {
    setFormData((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const validateForm = () => {
    const { first_name, last_name, email, phone_number, dob, password, confirm_password } = formData;

    if (!first_name || !last_name || !email || !phone_number || !dob || !password || !confirm_password) {
      setError("All required fields must be filled");
      return false;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError("Invalid email format");
      return false;
    }

    if (!/^\+?[0-9]{10,13}$/.test(phone_number)) {
      setError("Invalid phone number format");
      return false;
    }

    if (password !== confirm_password) {
      setError("Passwords do not match");
      return false;
    }

    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setSuccess("");

    if (!validateForm()) return;

    setLoading(true);

    try {
      const response = await fetch("http://127.0.0.1:8000/api/auth/register/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });

      const text = await response.text();
      let data = {};
      try { data = JSON.parse(text); } catch { data = { error: text }; }

      if (!response.ok) throw new Error(data.message || "Registration failed");

      setSuccess(data.message || "Registration successful");
      setFormData({
        first_name: "",
        middle_name: "",
        last_name: "",
        email: "",
        phone_number: "",
        dob: "",
        password: "",
        confirm_password: "",
      });

      setTimeout(() => { window.location.href = "/login"; }, 1500);
    } catch (err) {
      setError(err.message || "Unexpected error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-register-root">
      <div className="mt-login-card">
        {/* LEFT FORM */}
        <div className="mt-login-left">
          <img src={Logo} alt="Mero Ticket Logo" className="mt-logo" />
          <h2 className="mt-title">Create Account</h2>
          <p className="mt-subtitle">Fill in your details to register</p>

          <form className="mt-form" onSubmit={handleSubmit}>
            {/* Phone */}
            <label className="mt-label">
              Phone Number *
              <div className="mt-input-wrapper">
                <span className="mt-icon material-symbols-outlined">phone</span>
                <input
                  type="tel"
                  name="phone_number"
                  placeholder="+977 Enter your Phone Number"
                  value={formData.phone_number}
                  onChange={handleChange}
                  disabled={loading}
                  required
                />
              </div>
            </label>

            {/* Email */}
            <label className="mt-label">
              Email *
              <div className="mt-input-wrapper">
                <span className="mt-icon material-symbols-outlined">email</span>
                <input
                  type="email"
                  name="email"
                  placeholder="Enter your Email"
                  value={formData.email}
                  onChange={handleChange}
                  disabled={loading}
                  required
                />
              </div>
            </label>

            {/* Date of Birth */}
            <label className="mt-label">
              Date of Birth *
              <div className="mt-input-wrapper">
                <span className="mt-icon material-symbols-outlined">calendar_month</span>
                <input
                  type="date"
                  name="dob"
                  value={formData.dob}
                  onChange={handleChange}
                  disabled={loading}
                  required
                />
              </div>
            </label>

            <div className="mt-name-row">
              <div>
                <div className="mt-inline-label">First Name *</div>
                <div className="mt-input-wrapper">
                  <span className="mt-icon material-symbols-outlined">person</span>
                  <input
                    type="text"
                    name="first_name"
                    placeholder="First Name"
                    value={formData.first_name}
                    onChange={handleChange}
                    disabled={loading}
                    required
                  />
                </div>
              </div>
              <div>
                <div className="mt-inline-label">Middle Name</div>
                <div className="mt-input-wrapper">
                  <span className="mt-icon material-symbols-outlined">person</span>
                  <input
                    type="text"
                    name="middle_name"
                    placeholder="Middle Name"
                    value={formData.middle_name}
                    onChange={handleChange}
                    disabled={loading}
                  />
                </div>
              </div>
              <div>
                <div className="mt-inline-label">Last Name *</div>
                <div className="mt-input-wrapper">
                  <span className="mt-icon material-symbols-outlined">person</span>
                  <input
                    type="text"
                    name="last_name"
                    placeholder="Last Name"
                    value={formData.last_name}
                    onChange={handleChange}
                    disabled={loading}
                    required
                  />
                </div>
              </div>
            </div>

            {/* Password */}
            <label className="mt-label">
              Password *
              <div className="mt-input-wrapper">
                <span className="mt-icon material-symbols-outlined">key</span>
                <input
                  type={showPassword ? "text" : "password"}
                  name="password"
                  placeholder="Enter password"
                  value={formData.password}
                  onChange={handleChange}
                  disabled={loading}
                  required
                />
                <button type="button" className="mt-eye-btn" onClick={() => setShowPassword(!showPassword)}>
                  <span className="material-symbols-outlined">
                    {showPassword ? "visibility_off" : "visibility"}
                  </span>
                </button>
              </div>
            </label>

            {/* Confirm Password */}
            <label className="mt-label">
              Confirm Password *
              <div className="mt-input-wrapper">
                <span className="mt-icon material-symbols-outlined">key</span>
                <input
                  type={showPassword ? "text" : "password"}
                  name="confirm_password"
                  placeholder="Confirm password"
                  value={formData.confirm_password}
                  onChange={handleChange}
                  disabled={loading}
                  required
                />
              </div>
            </label>

            {error && <div className="mt-error">{error}</div>}
            {success && <div className="mt-success">{success}</div>}

            <button type="submit" className="mt-primary-btn" disabled={loading}>
              {loading ? "Creating account..." : "Sign Up"}
            </button>

            <div className="mt-footer-text">
              Already have an account?{" "}
              <button type="button" className="mt-cta" onClick={() => (window.location.href = "/login")}>
                Sign In
              </button>
            </div>
          </form>
        </div>

        {/* RIGHT SIDE - HERO SLIDER */}
        <div
          className="mt-login-right"
          style={{ backgroundImage: `url(${heroImages[currentSlide]})` }}
        >
          <div className="mt-hero-card-overlay">
            <div className="mt-hero-badge">For Movie Lovers</div>
            <h2>Join Mero Ticket today</h2>
            <p>Create an account to access exclusive deals and personalized recommendations.</p>
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

export default RegisterPage;
