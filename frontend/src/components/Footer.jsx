import React, { useState } from "react";
import { ArrowRight, Copy, Facebook, Instagram, Linkedin, Twitter } from "lucide-react";
import "../css/layout.css";

export default function Footer() {
  const year = new Date().getFullYear();
  const [copied, setCopied] = useState(false);

  const handleCopyEmail = async () => {
    try {
      await navigator.clipboard.writeText("support@meroticket.com");
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };

  return (
    <footer className="wf2-footerShell">
      <div className="wf2-container">
        <div className="wf2-constrained wf2-footerCard">
          <div className="wf2-footerTopRow">
            <section className="wf2-footerLead">
              <span className="wf2-footerKicker">Contact us</span>
              <h2 className="wf2-footerHeading">Let's discuss your vision. With us</h2>

              <a className="wf2-footerCta" href="/contact">
                <span>Schedule a call now</span>
                <ArrowRight size={18} strokeWidth={2.2} aria-hidden="true" />
              </a>

              <div className="wf2-footerEmailWrap">
                <span className="wf2-footerEmailLabel">Or email us at</span>
                <button type="button" className="wf2-footerEmailBtn" onClick={handleCopyEmail}>
                  <span>{copied ? "Email copied" : "support@meroticket.com"}</span>
                  <Copy size={16} strokeWidth={2} aria-hidden="true" />
                </button>
              </div>
            </section>

            <div className="wf2-footerLinksWrap">
              <nav className="wf2-footerCol" aria-label="Quick links">
                <h3 className="wf2-footerTitle">Quick links</h3>
                <a className="wf2-footerLink" href="/">Home</a>
                <a className="wf2-footerLink" href="/movies">Movies</a>
                <a className="wf2-footerLink" href="/cinemas">Cinemas</a>
                <a className="wf2-footerLink" href="/offers">Offers</a>
                <a className="wf2-footerLink" href="/about">About us</a>
              </nav>

              <nav className="wf2-footerCol" aria-label="Information">
                <h3 className="wf2-footerTitle">Information</h3>
                <a className="wf2-footerLink" href="/terms">Terms of service</a>
                <a className="wf2-footerLink" href="/privacy">Privacy policy</a>
                <a className="wf2-footerLink" href="/cookies">Cookies settings</a>
              </nav>
            </div>
          </div>

          <div className="wf2-footerDivider" aria-hidden="true" />

          <div className="wf2-footerBottomRow">
            <p className="wf2-footerLegal">Copyright {year} Mero Ticket. All rights reserved.</p>
            <div className="wf2-footerSocials" aria-label="Social links">
              <a className="wf2-footerSocial" href="https://facebook.com" target="_blank" rel="noreferrer" aria-label="Facebook">
                <Facebook size={15} strokeWidth={2} />
              </a>
              <a className="wf2-footerSocial" href="https://twitter.com" target="_blank" rel="noreferrer" aria-label="Twitter">
                <Twitter size={15} strokeWidth={2} />
              </a>
              <a className="wf2-footerSocial" href="https://instagram.com" target="_blank" rel="noreferrer" aria-label="Instagram">
                <Instagram size={15} strokeWidth={2} />
              </a>
              <a className="wf2-footerSocial" href="https://linkedin.com" target="_blank" rel="noreferrer" aria-label="LinkedIn">
                <Linkedin size={15} strokeWidth={2} />
              </a>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
