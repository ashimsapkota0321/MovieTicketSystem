import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, Download } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import "../css/orderConfirm.css";
import gharjwai from "../images/gharjwai.jpg";
import html2canvas from "html2canvas";
import { getCinemaBySlug, resolveCinemaSlug } from "../lib/cinemas";
import { API_BASE_URL } from "../lib/apiBase";
const SUPPORT_CONTACT = "+977 9826633701";
const WEBSITE_URL = "www.meroticket.com";

const DEFAULT_ORDER = {
  movie: {
    title: "Hami Teen Bhai",
    language: "Nepali",
    runtime: "2h 10m",
    seat: "Seat No: A12, A13",
    venue: "QFX Civil Mall, 18 Feb 2026, 08:30 PM",
    poster: gharjwai,
  },
  ticketTotal: 600,
  items: [],
  foodTotal: 0,
  total: 600,
};

const parseTicketDetails = (html) => {
  if (!html || typeof window === "undefined") return null;
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  const labels = Array.from(doc.querySelectorAll(".label"));
  const values = Array.from(doc.querySelectorAll(".value"));
  const data = {};
  labels.forEach((label, index) => {
    const key = label.textContent?.trim().toLowerCase();
    const value = values[index]?.textContent?.trim();
    if (key) {
      data[key] = value || "";
    }
  });
  return data;
};

export default function TicketDownload() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location?.state;
  const ticket = state?.ticket || {};
  const [remoteDetails, setRemoteDetails] = useState(null);
  const ticketRef = useRef(null);

  const order = useMemo(() => {
    const rawOrder = state?.order || {};
    const items = Array.isArray(rawOrder.items)
      ? rawOrder.items
      : DEFAULT_ORDER.items;
    const ticketTotal =
      typeof rawOrder.ticketTotal === "number"
        ? rawOrder.ticketTotal
        : DEFAULT_ORDER.ticketTotal;
    const movie = rawOrder.movie || DEFAULT_ORDER.movie;
    const foodTotal =
      typeof rawOrder.foodTotal === "number"
        ? rawOrder.foodTotal
        : items.reduce((sum, item) => sum + item.price * item.qty, 0);
    const total =
      typeof rawOrder.total === "number" ? rawOrder.total : ticketTotal + foodTotal;
    return {
      movie,
      ticketTotal,
      items,
      foodTotal,
      total,
    };
  }, [state]);

  useEffect(() => {
    const refFromQuery = new URLSearchParams(location.search).get("ref");
    const ref = ticket?.reference || refFromQuery;
    const detailsUrl = ticket?.details_url || (ref ? `${API_BASE_URL}/ticket/${ref}/details/` : "");
    if (!detailsUrl) return;

    let active = true;
    fetch(detailsUrl, { headers: { Accept: "text/html" } })
      .then((res) => (res.ok ? res.text() : Promise.reject(new Error("Failed to load"))))
      .then((html) => {
        if (!active) return;
        const parsed = parseTicketDetails(html);
        if (parsed) {
          setRemoteDetails(parsed);
        }
      })
      .catch(() => {
        if (active) {
          setRemoteDetails(null);
        }
      });

    return () => {
      active = false;
    };
  }, [ticket?.details_url, ticket?.reference, location.search]);

  const formatPrice = (value) => `Npr ${value}`;

  const downloadUrl = useMemo(() => {
    const providedUrl = ticket?.download_url || ticket?.ticket_image;
    if (providedUrl) return providedUrl;

    const refFromQuery = new URLSearchParams(location.search).get("ref");
    const reference = String(ticket?.reference || refFromQuery || "").trim();
    if (!reference) return "";
    return `${API_BASE_URL}/ticket/${encodeURIComponent(reference)}/download/`;
  }, [location.search, ticket?.download_url, ticket?.reference, ticket?.ticket_image]);

  const triggerDownload = useCallback((href, filename) => {
    const link = document.createElement("a");
    link.href = href;
    link.download = filename;
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }, []);

  const handleDownload = useCallback(async () => {
    const filename = `ticket-${ticket.reference || "mero"}.png`;
    const node = ticketRef.current;
    if (node) {
      try {
        const canvas = await html2canvas(node, {
          backgroundColor: null,
          scale: 2,
          useCORS: true,
        });
        triggerDownload(canvas.toDataURL("image/png"), filename);
        return;
      } catch {
        // fallback to backend download
      }
    }
    if (downloadUrl) {
      triggerDownload(downloadUrl, filename);
    }
  }, [downloadUrl, ticket.reference, triggerDownload]);

  useEffect(() => {
    if (!state?.autoDownload) return;
    const timer = setTimeout(() => {
      handleDownload();
    }, 350);
    return () => clearTimeout(timer);
  }, [state?.autoDownload, handleDownload]);

  const ticketDetails = remoteDetails || {};
  const reviewState = getTicketReviewState(ticket, ticketDetails);
  const venueParts = String(order.movie.venue || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);

  const fallbackCinemaName =
    order.movie.cinemaName || venueParts[0] || order.movie.venue || "-";
  const cinemaName = ticketDetails["cinema hall"] || fallbackCinemaName;
  const cinemaBrand = resolveCinemaBrand(cinemaName);
  const cinemaLocation =
    order.movie.cinemaLocation ||
    order.movie.location ||
    extractLocationFromVenue(order.movie.venue, cinemaBrand.name) ||
    "-";

  const showDate = ticketDetails.date || order.movie.showDate || venueParts[1] || "";
  const showTime = ticketDetails.time || order.movie.showTime || venueParts[2] || "";
  const theater = ticketDetails.theater || order.movie.theater || order.movie.hall || "03";
  const seatLabel = normalizeSeatLabel(ticketDetails.seat || order.movie.seat);
  const movieTitle = ticketDetails.movie || order.movie.title || "Movie";
  const formattedDate = formatDateLabel(showDate);
  const formattedTime = formatTimeLabel(showTime);

  const ticketTotalLabel = ticketDetails["ticket total"] || formatPrice(order.ticketTotal);
  const foodTotalLabel = ticketDetails["food total"] || formatPrice(order.foodTotal);
  const grandTotalLabel = ticketDetails["grand total"] || formatPrice(order.total);
  const ticketId = ticket?.ticket_id || ticket?.reference || "MT-XXXX";

  const ticketStyle = useMemo(
    () => ({ "--wf2-ticket-accent": cinemaBrand.accent || "#0f6fbf" }),
    [cinemaBrand.accent]
  );

  return (
    <div className="wf2-orderPage wf2-ticketPage">
      <div className="wf2-orderHeader">
        <button
          className="wf2-orderBack"
          type="button"
          onClick={() => navigate(-1)}
          aria-label="Go back"
        >
          <ChevronLeft size={18} />
        </button>
        <div className="wf2-orderHeaderText">
          <h2 className="wf2-orderTitle">Ticket Download</h2>
          <p className="wf2-orderSubtitle">
            Your ticket is ready. Download it or save the QR for entry.
          </p>
        </div>
      </div>

      <div className={`wf2-lifecycleAlert ${reviewState.className}`}>
        {reviewState.label}
      </div>

      <div className="wf2-orderLayout">
        <div className="wf2-orderMain">
          <section className="wf2-orderPanel wf2-ticketPreviewPanel">
            <div className="wf2-orderPanelHeader">
              <h3 className="wf2-orderPanelTitle">Ticket Preview</h3>
              {ticket?.reference ? (
                <span className="wf2-orderChip">Ref {ticket.reference}</span>
              ) : null}
            </div>

            <div className="wf2-ticketFrame" ref={ticketRef} style={ticketStyle}>
              <article className="wf2-etkShell">
                <section className="wf2-etkMain">
                  <header className="wf2-etkHead">
                    <div className="wf2-etkLogo">Mero Ticket</div>
                    <div className="wf2-etkVendorBlock">
                      <div className="wf2-etkVendorName">{cinemaBrand.name}</div>
                      <div className="wf2-etkVendorLocation">{cinemaLocation}</div>
                    </div>
                    <span className="wf2-etkType">E-TICKET</span>
                  </header>

                  <h3 className="wf2-etkMovieTitle">{movieTitle}</h3>

                  <div className="wf2-etkHighlightRow">
                    <div className="wf2-etkHighlightCell">
                      <span>Show Date</span>
                      <strong>{formattedDate}</strong>
                    </div>
                    <div className="wf2-etkHighlightCell">
                      <span>Show Time</span>
                      <strong>{formattedTime}</strong>
                    </div>
                    <div className="wf2-etkHighlightCell">
                      <span>Seats</span>
                      <strong>{seatLabel}</strong>
                    </div>
                  </div>

                  <div className="wf2-etkGrid">
                    <div className="wf2-etkGridItem">
                      <span>Movie</span>
                      <strong>{movieTitle}</strong>
                    </div>
                    <div className="wf2-etkGridItem">
                      <span>Cinema</span>
                      <strong>{cinemaBrand.name}</strong>
                    </div>
                    <div className="wf2-etkGridItem">
                      <span>Screen</span>
                      <strong>{theater}</strong>
                    </div>
                    <div className="wf2-etkGridItem">
                      <span>Ticket ID</span>
                      <strong>{ticketId}</strong>
                    </div>
                  </div>

                  <footer className="wf2-etkFooter">
                    <div className="wf2-etkTotals">
                      <div>
                        <span>Ticket Price</span>
                        <strong>{ticketTotalLabel}</strong>
                      </div>
                      <div>
                        <span>Food Price</span>
                        <strong>{foodTotalLabel}</strong>
                      </div>
                      <div className="wf2-etkTotalFinal">
                        <span>Total Amount</span>
                        <strong>{grandTotalLabel}</strong>
                      </div>
                    </div>
                    <div className="wf2-etkContact">
                      <div>Support: {SUPPORT_CONTACT}</div>
                      <div>Website: {WEBSITE_URL}</div>
                    </div>
                  </footer>
                </section>

                <aside className="wf2-etkSide">
                  <div className="wf2-etkQrWrap">
                    {ticket?.qr_code ? (
                      <img className="wf2-ticketQr" src={ticket.qr_code} alt="Entry QR code" />
                    ) : (
                      <div className="wf2-ticketQrPlaceholder">QR code not available.</div>
                    )}
                  </div>
                  <div className="wf2-etkTicketMeta">
                    <span>Ticket ID</span>
                    <strong>{ticketId}</strong>
                  </div>
                  <p className="wf2-etkSideHint">Scan this QR at cinema entry.</p>
                </aside>
              </article>
            </div>
          </section>

          <section className="wf2-orderPanel">
            <div className="wf2-orderPanelHeader">
              <h3 className="wf2-orderPanelTitle">Ticket Details</h3>
            </div>
            <div className="wf2-ticketDetailGrid">
              <div>
                <div className="wf2-ticketDetailLabel">Movie</div>
                <div className="wf2-ticketDetailValue">{movieTitle}</div>
              </div>
              <div>
                <div className="wf2-ticketDetailLabel">Language</div>
                <div className="wf2-ticketDetailValue">{order.movie.language}</div>
              </div>
              <div>
                <div className="wf2-ticketDetailLabel">Runtime</div>
                <div className="wf2-ticketDetailValue">{order.movie.runtime}</div>
              </div>
              <div>
                <div className="wf2-ticketDetailLabel">Seats</div>
                <div className="wf2-ticketDetailValue">{seatLabel}</div>
              </div>
              <div>
                <div className="wf2-ticketDetailLabel">Venue</div>
                <div className="wf2-ticketDetailValue">{cinemaBrand.name}</div>
              </div>
              <div>
                <div className="wf2-ticketDetailLabel">Location</div>
                <div className="wf2-ticketDetailValue">{cinemaLocation}</div>
              </div>
            </div>
          </section>
        </div>

        <aside className="wf2-orderSidebar">
          <section className="wf2-orderPanel">
            <div className="wf2-orderPanelHeader">
              <h3 className="wf2-orderPanelTitle">Download Ticket</h3>
            </div>
            <div className="wf2-ticketDownloadNote">
              Save the ticket image to your device. Present it at entry if needed.
            </div>
            <button
              className="wf2-orderDownloadBtn"
              type="button"
              onClick={handleDownload}
              disabled={!downloadUrl || reviewState.blockDownload}
            >
              <Download size={18} /> Download Ticket
            </button>
            <button
              className="wf2-orderGhostBtn"
              type="button"
              onClick={() => navigate("/thank-you", { state: { order, ticket } })}
            >
              Back to Thank You
            </button>
          </section>
        </aside>
      </div>
    </div>
  );
}

function resolveCinemaBrand(value) {
  const raw = String(value || "").trim();
  const slug = resolveCinemaSlug(raw);
  const match = slug ? getCinemaBySlug(slug) : null;
  return {
    name: match?.name || raw || "Cinema",
    accent: match?.accent || "#0f6fbf",
  };
}

function normalizeSeatLabel(value) {
  const text = String(value || "").trim();
  if (!text) return "-";
  const cleaned = text.replace(/seat\s*no\s*[:#-]?\s*/i, "").trim();
  return cleaned || "-";
}

function formatDateLabel(value) {
  const text = String(value || "").trim();
  if (!text) return "-";
  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    const date = new Date(`${text}T00:00:00`);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      });
    }
  }
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  return date.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatTimeLabel(value) {
  const text = String(value || "").trim();
  if (!text) return "-";
  if (text.toLowerCase().includes("am") || text.toLowerCase().includes("pm")) {
    return text.toUpperCase();
  }
  const match = text.match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return text;
  let hour = Number(match[1]);
  const minute = Number(match[2]);
  if (Number.isNaN(hour) || Number.isNaN(minute)) return text;
  const period = hour >= 12 ? "PM" : "AM";
  hour = hour % 12 || 12;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")} ${period}`;
}

function getTicketReviewState(ticket, details) {
  const approvalStatus = String(
    ticket?.approvalStatus || ticket?.approval_status || details?.approvalStatus || details?.approval_status || ""
  )
    .trim()
    .toUpperCase();
  const reviewStatus = String(
    ticket?.reviewStatus || ticket?.review_status || details?.reviewStatus || details?.review_status || ""
  )
    .trim()
    .toUpperCase();
  const paymentStatus = String(
    ticket?.paymentStatus || ticket?.payment_status || details?.paymentStatus || details?.payment_status || ""
  )
    .trim()
    .toUpperCase();

  if (approvalStatus === "PENDING" || reviewStatus === "PENDING") {
    return {
      label: "Review pending. The ticket is not ready for download yet.",
      className: "wf2-lifecycleAlertWarning",
      blockDownload: true,
    };
  }
  if (approvalStatus === "REJECTED" || reviewStatus === "REJECTED") {
    return {
      label: "Review rejected. Please wait for support to issue a new ticket.",
      className: "wf2-lifecycleAlertDanger",
      blockDownload: true,
    };
  }
  if (paymentStatus === "PENDING") {
    return {
      label: "Payment pending. Download will unlock after confirmation.",
      className: "wf2-lifecycleAlertWarning",
      blockDownload: true,
    };
  }
  return {
    label: "Ticket is approved and ready for download.",
    className: "wf2-lifecycleAlertSuccess",
    blockDownload: false,
  };
}

function extractLocationFromVenue(venue, cinemaName) {
  const rawVenue = String(venue || "").trim();
  if (!rawVenue) return "";
  const firstChunk = rawVenue.split(",")[0]?.trim() || "";
  if (!firstChunk) return "";
  const normalizedCinema = normalizeText(cinemaName);
  const normalizedChunk = normalizeText(firstChunk);
  if (!normalizedCinema) return firstChunk;
  if (normalizedChunk === normalizedCinema) return "";
  if (normalizedChunk.startsWith(normalizedCinema)) {
    return firstChunk.slice(cinemaName.length).replace(/^[-:,\s]+/, "").trim();
  }
  return firstChunk;
}

function normalizeText(value) {
  return String(value || "").trim().toLowerCase();
}
