import React from "react";
import "../css/layout.css";

export default function Footer() {
  const year = new Date().getFullYear();
  return (
    <>
      <footer className="wf2-footer">
        <div className="wf2-container">
          <div className="wf2-constrained wf2-footerGrid">
            <div className="wf2-footerIntro">
              <div className="wf2-footerBrand">Mero Ticket</div>
              <p className="wf2-footerText">
                Book Nepali movies and local cinema events fast. Pick seats, pay
                securely, and get mobile tickets instantly.
              </p>
              <div className="wf2-footerHighlights">
                <span className="wf2-footerHighlight">Instant tickets</span>
                <span className="wf2-footerHighlight">Secure payment</span>
                <span className="wf2-footerHighlight">Seat selection</span>
              </div>
            </div>

            <div className="wf2-footerCol">
              <div className="wf2-footerTitle">Explore</div>
              <a className="wf2-footerLink" href="/movies">Movies</a>
              <a className="wf2-footerLink" href="/schedules">Showtimes</a>
              <a className="wf2-footerLink" href="/cinemas">Cinemas</a>
              <a className="wf2-footerLink" href="/booking">Booking</a>
            </div>

            <div className="wf2-footerCol">
              <div className="wf2-footerTitle">Account</div>
              <a className="wf2-footerLink" href="/login">Login</a>
              <a className="wf2-footerLink" href="/register">Create account</a>
              <a className="wf2-footerLink" href="/forgot-password">Reset password</a>
            </div>

            <div className="wf2-footerCol">
              <div className="wf2-footerTitle">Contact</div>
              <div className="wf2-footerSmall">support@meroticket.com</div>
              <div className="wf2-footerSmall">+977 9826633701</div>
              <div className="wf2-footerSmall">Pokhara, Nepal</div>
            </div>
          </div>
        </div>
      </footer>
      <div className="wf2-footerLegal">
        Copyright {year} Mero Ticket. All rights reserved.
      </div>
    </>
  );
}
