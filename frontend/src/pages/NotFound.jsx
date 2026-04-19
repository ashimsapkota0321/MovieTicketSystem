import React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft, House, TriangleAlert } from "lucide-react";
import notFoundImg from "../assets/not-found.png";
import "../css/not-found.css";

function NotFound() {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <section className="http-error-page" role="main" aria-labelledby="http-error-title">
      <div className="http-error-card">
        <div className="http-error-code-wrap">
          <span className="http-error-badge">
            <TriangleAlert size={15} />
            HTTP Error
          </span>
          <h1 className="http-error-code">404</h1>
          <h2 id="http-error-title" className="http-error-title">Page Not Found</h2>
          <p className="http-error-text">
            यो पेज भेटिएन। The link may be outdated, removed, or typed incorrectly.
          </p>
        </div>

        <div className="http-error-preview" aria-hidden="true">
          <img className="http-error-image" src={notFoundImg} alt="" />
        </div>

        <div className="http-error-path" title={location.pathname}>
          Requested URL: <strong>{location.pathname}</strong>
        </div>

        <div className="http-error-actions">
          <button
            type="button"
            className="http-error-btn http-error-btn--primary"
            onClick={() => navigate("/")}
          >
            <House size={17} />
            Go To Home
          </button>
          <button
            type="button"
            className="http-error-btn http-error-btn--ghost"
            onClick={() => navigate(-1)}
          >
            <ArrowLeft size={17} />
            Go Back
          </button>
        </div>
      </div>
    </section>
  );
}

export default NotFound;
