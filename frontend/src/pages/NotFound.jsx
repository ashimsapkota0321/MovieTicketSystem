import React from "react";
import notFoundImg from "../assets/not-found.png";
import "../css/not-found.css";

function NotFound() {
  return (
    <div className="not-found">
      <img
        className="not-found__image"
        src={notFoundImg}
        alt="Page not found"
      />
    </div>
  );
}

export default NotFound;
