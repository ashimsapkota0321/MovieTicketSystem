import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, Download } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import "../css/orderConfirm.css";
import gharjwai from "../images/gharjwai.jpg";
import html2canvas from "html2canvas";

const API_BASE_URL = "http://localhost:8000/api";

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
  const state = location?.state || {};
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

  const downloadUrl = ticket?.download_url || ticket?.ticket_image;

  const triggerDownload = (href, filename) => {
    const link = document.createElement("a");
    link.href = href;
    link.download = filename;
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
  };

  const handleDownload = async () => {
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
      } catch (err) {
        // fallback to backend download
      }
    }
    if (downloadUrl) {
      triggerDownload(downloadUrl, filename);
    }
  };

  useEffect(() => {
    if (!state?.autoDownload) return;
    const timer = setTimeout(() => {
      handleDownload();
    }, 350);
    return () => clearTimeout(timer);
  }, [state?.autoDownload, downloadUrl]);

  const ticketDetails = remoteDetails || {};
  const venueParts = String(order.movie.venue || "").split(",").map((part) => part.trim()).filter(Boolean);
  const venueName = ticketDetails["cinema hall"] || venueParts[0] || order.movie.venue || "-";
  const showDate = ticketDetails["date"] || venueParts[1] || "";
  const showTime = ticketDetails["time"] || venueParts[2] || "";
  const theater = ticketDetails["theater"] || "03";
  const seatLabel = ticketDetails["seat"] || order.movie.seat;
  const ticketTotalLabel = ticketDetails["ticket total"] || formatPrice(order.ticketTotal);
  const foodTotalLabel = ticketDetails["food total"] || formatPrice(order.foodTotal);
  const grandTotalLabel = ticketDetails["grand total"] || formatPrice(order.total);
  const displayDate = showDate || "Friday, July 26th";
  const displayName = ticketDetails["name"] || "Guest User";
  const displayWebsite = "www.meroticket.com";

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

      <div className="wf2-orderLayout">
        <div className="wf2-orderMain">
          <section className="wf2-orderPanel wf2-ticketPreviewPanel">
            <div className="wf2-orderPanelHeader">
              <h3 className="wf2-orderPanelTitle">Ticket Preview</h3>
              {ticket?.reference ? (
                <span className="wf2-orderChip">Ref {ticket.reference}</span>
              ) : null}
            </div>
            <div className="wf2-ticketFrame" ref={ticketRef}>
              <div className="wf2-ticketStripe">
                <span />
                <span />
                <span />
                <span />
              </div>
              <div className="wf2-ticketCard">
              <div className="wf2-ticketLeft">
                <div className="wf2-ticketBrand">MERO TICKET</div>
                <div className="wf2-ticketTitle">Welcome to {venueName}</div>
                <div className="wf2-ticketSubtitle">
                  {ticketDetails.movie || order.movie.title}
                </div>
                <div className="wf2-ticketInfoBox">
                  <div className="wf2-ticketInfoItem">
                    <span>E-ticket</span>
                  </div>
                  <div className="wf2-ticketInfoItem">
                    <strong>Name: {displayName}</strong>
                    <span>ID: {ticket?.reference || "MT-XXXX"}</span>
                  </div>
                  <div className="wf2-ticketInfoItem">
                    <strong>{displayDate}</strong>
                  </div>
                  <div className="wf2-ticketInfoItem">
                    <strong>{displayWebsite}</strong>
                  </div>
                </div>
                <div className="wf2-ticketMetaRows">
                  <div><span>Cinema</span> {venueName}</div>
                  <div><span>Theater</span> {theater}</div>
                  <div><span>Seat</span> {seatLabel}</div>
                  <div><span>Date</span> {showDate || "-"}</div>
                  <div><span>Time</span> {showTime || "-"}</div>
                </div>
                <div className="wf2-ticketTotals">
                  <div><span>Ticket</span><strong>{ticketTotalLabel}</strong></div>
                  <div><span>Food</span><strong>{foodTotalLabel}</strong></div>
                  <div><span>Total</span><strong>{grandTotalLabel}</strong></div>
                </div>
              </div>
              <div className="wf2-ticketRight">
                <div className="wf2-ticketQrWrap">
                  {ticket?.qr_code ? (
                    <img className="wf2-ticketQr" src={ticket.qr_code} alt="Entry QR code" />
                  ) : (
                    <div className="wf2-ticketQrPlaceholder">QR code not available.</div>
                  )}
                </div>
                <div className="wf2-ticketSideText">
                  Please present this ticket at the entrance
                </div>
                <div className="wf2-ticketRef">Questions? +977 9826633701</div>
              </div>
              </div>
            </div>
          </section>

          <section className="wf2-orderPanel">
            <div className="wf2-orderPanelHeader">
              <h3 className="wf2-orderPanelTitle">Ticket Details</h3>
            </div>
            <div className="wf2-ticketDetailGrid">
              <div>
                <div className="wf2-ticketDetailLabel">Movie</div>
                <div className="wf2-ticketDetailValue">{ticketDetails.movie || order.movie.title}</div>
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
                <div className="wf2-ticketDetailValue">{venueName}</div>
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
              disabled={!downloadUrl}
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
