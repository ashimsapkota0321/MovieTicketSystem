import React, { useMemo } from "react";
import { CheckCircle, Download } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import "../css/orderConfirm.css";

const DEFAULT_ORDER = {
  movie: {
    title: "Hami Teen Bhai",
    language: "Nepali",
    runtime: "2h 10m",
    seat: "Seat No: A12, A13",
    venue: "QFX Civil Mall, 18 Feb 2026, 08:30 PM",
  },
  ticketTotal: 600,
  items: [],
  foodTotal: 0,
  total: 600,
};

export default function ThankYou() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location?.state || {};
  const ticket = state?.ticket || {};

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

  const formatPrice = (value) => `Npr ${Number(value || 0).toLocaleString()}`;

  const handleGoDownload = (autoDownload = false) => {
    navigate("/ticket-download", {
      state: {
        order,
        ticket,
        autoDownload,
      },
    });
  };

  return (
    <div className="wf2-thankyouPage">
      <div className="wf2-thankyouContainer">
        <div className="wf2-thankyouHero">
          <div className="wf2-thankyouCheck">
            <CheckCircle size={22} />
          </div>
          <h1 className="wf2-thankyouTitle">Thank You</h1>
          <p className="wf2-thankyouSubtext">
            Your booking is confirmed. Keep your QR code ready at the entry gate.
          </p>
        </div>

        <div className="wf2-lifecycleGrid wf2-thankyouLifecycleGrid">
          <div className="wf2-lifecycleCard">
            <span>Payment</span>
            <strong>Confirmed</strong>
            <p>The gateway payment has been validated and attached to the booking.</p>
          </div>
          <div className="wf2-lifecycleCard">
            <span>Ticket</span>
            <strong>Ready</strong>
            <p>The QR and download handoff are available below.</p>
          </div>
          <div className="wf2-lifecycleCard">
            <span>Review</span>
            <strong>Closed</strong>
            <p>No manual approval is needed for this confirmed ticket.</p>
          </div>
        </div>

        <div className="wf2-thankyouRow">
          <section className="wf2-thankyouCard wf2-thankyouQrCard">
            <h3>Entry QR Code</h3>
            {ticket?.qr_code ? (
              <img className="wf2-thankyouQr" src={ticket.qr_code} alt="Entry QR code" />
            ) : (
              <div className="wf2-thankyouQrPlaceholder">
                QR code not available. Please try again.
              </div>
            )}
            <p>Show this QR at the entry gate.</p>
            <div className="wf2-thankyouRef">
              {ticket?.reference ? `Ref ${ticket.reference}` : "Ref Pending"}
            </div>
          </section>

          <section className="wf2-thankyouCard">
            <h3>Download Ticket</h3>
            <p>Save your ticket for offline access or sharing.</p>
            <button
              className="wf2-thankyouBtnPrimary"
              type="button"
              onClick={() => handleGoDownload(true)}
            >
              <Download size={18} /> Download Ticket
            </button>
            <button className="wf2-thankyouBtnGhost" type="button" onClick={() => handleGoDownload(false)}>
              Open Ticket Details
            </button>
          </section>
        </div>

        <div className="wf2-thankyouSummary">
          <div className="wf2-thankyouSummaryItem">
            <span>Movie</span>
            <strong>{order.movie.title}</strong>
          </div>
          <div className="wf2-thankyouSummaryItem">
            <span>Language · Runtime</span>
            <strong>{order.movie.language} · {order.movie.runtime}</strong>
          </div>
          <div className="wf2-thankyouSummaryItem">
            <span>Seats</span>
            <strong>{order.movie.seat}</strong>
          </div>
          <div className="wf2-thankyouSummaryItem">
            <span>Venue</span>
            <strong>{order.movie.venue}</strong>
          </div>
          <div className="wf2-thankyouSummaryItem">
            <span>Total Paid</span>
            <strong>{formatPrice(order.total)}</strong>
          </div>
        </div>

        <div className="wf2-thankyouFooterActions">
          <button className="wf2-thankyouBtnGhost" type="button" onClick={() => navigate("/movies")}>
            Browse Movies
          </button>
          <button className="wf2-thankyouBtnGhost" type="button" onClick={() => navigate("/")}>
            Go Home
          </button>
        </div>
      </div>
    </div>
  );
}
