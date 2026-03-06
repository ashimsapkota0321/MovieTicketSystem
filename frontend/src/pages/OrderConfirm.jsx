import React, { useMemo, useState } from "react";
import { ChevronLeft } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import "../css/orderConfirm.css";
import gharjwai from "../images/gharjwai.jpg";

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
  items: [
    {
      id: "popcorn-salt",
      name: "Regular Salt Pop Corn 80g",
      desc: "Allergen: Milk | Popcorn 80g | 425 kcal",
      price: 300,
      qty: 1,
    },
    {
      id: "popcorn-cheese",
      name: "Cheese Pop Corn 80g",
      desc: "Allergen: Milk | Popcorn 80g | 435 kcal",
      price: 300,
      qty: 1,
    },
  ],
};

const API_BASE_URL =
  `${import.meta.env.VITE_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000"}/api`;

export default function OrderConfirm() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location?.state || {};

  const order = useMemo(() => {
    const items = Array.isArray(state.items) ? state.items : DEFAULT_ORDER.items;
    const ticketTotal =
      typeof state.ticketTotal === "number" ? state.ticketTotal : DEFAULT_ORDER.ticketTotal;
    const movie = state.movie || DEFAULT_ORDER.movie;
    const selectedSeats = Array.isArray(state.selectedSeats)
      ? state.selectedSeats
      : extractSeatsFromLabel(movie?.seat);
    const bookingContext = {
      ...(state.bookingContext || {}),
      selectedSeats:
        Array.isArray(state?.bookingContext?.selectedSeats)
          ? state.bookingContext.selectedSeats
          : selectedSeats,
    };
    return {
      movie,
      ticketTotal,
      items,
      selectedSeats,
      bookingContext,
    };
  }, [state]);

  const foodTotal = order.items.reduce((sum, item) => sum + item.price * item.qty, 0);
  const foodCount = order.items.reduce((sum, item) => sum + (item.qty || 0), 0);
  const orderTotal = order.ticketTotal + foodTotal;
  const formatPrice = (value) => `Npr ${value}`;
  const [isPaying, setIsPaying] = useState(false);
  const [payError, setPayError] = useState("");

  const handlePayNow = async () => {
    if (isPaying) return;
    setIsPaying(true);
    setPayError("");
    try {
      const bookingPayload = {
        showId: order.bookingContext?.showId,
        movieId: order.bookingContext?.movieId || order.movie.movieId,
        cinemaId: order.bookingContext?.cinemaId || order.movie.cinemaId,
        hall: order.bookingContext?.hall || order.movie.hall,
        date: order.bookingContext?.date,
        time: order.bookingContext?.time,
        selectedSeats: order.selectedSeats,
        userId:
          order.bookingContext?.userId || getStoredUser()?.id || null,
      };
      const hasCompleteBookingContext = Boolean(
        bookingPayload.movieId &&
          bookingPayload.cinemaId &&
          bookingPayload.date &&
          bookingPayload.time &&
          Array.isArray(bookingPayload.selectedSeats) &&
          bookingPayload.selectedSeats.length
      );

      const payload = {
        order: {
          movie: {
            title: order.movie.title,
            seat: order.movie.seat,
            venue: order.movie.venue,
            cinemaName: order.movie.cinemaName,
            cinemaLocation: order.movie.cinemaLocation,
            language: order.movie.language,
            runtime: order.movie.runtime,
            hall: order.movie.hall || order.bookingContext?.hall,
            theater: order.movie.theater || order.bookingContext?.hall,
            showDate: order.movie.showDate || order.bookingContext?.date,
            showTime: order.movie.showTime || order.bookingContext?.time,
            movieId: order.movie.movieId || order.bookingContext?.movieId,
            cinemaId: order.movie.cinemaId || order.bookingContext?.cinemaId,
          },
          ticketTotal: order.ticketTotal,
          foodTotal,
          total: orderTotal,
          ...(hasCompleteBookingContext
            ? {
                selectedSeats: order.selectedSeats,
                booking: bookingPayload,
              }
            : {}),
          items: order.items.map((item) => ({
            name: item.name,
            qty: item.qty,
            price: item.price,
          })),
        },
      };

      const response = await fetch(`${API_BASE_URL}/payment/qr/`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.message || "Failed to generate QR code.");
      }

      setIsPaying(false);
      navigate("/thank-you", {
        state: {
          order: {
            movie: order.movie,
            ticketTotal: order.ticketTotal,
            items: order.items,
            foodTotal,
            total: orderTotal,
            selectedSeats: order.selectedSeats,
            bookingContext: order.bookingContext,
          },
          ticket: data,
        },
      });
    } catch (err) {
      setIsPaying(false);
      setPayError(err?.message || "Failed to generate QR code.");
    }
  };

  return (
    <div className="wf2-orderPage">
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
          <h2 className="wf2-orderTitle">Order Confirm</h2>
          <p className="wf2-orderSubtitle">
            Review your ticket and food items before payment.
          </p>
        </div>
      </div>

      <div className="wf2-orderLayout">
        <div className="wf2-orderMain">
          <section className="wf2-orderPanel">
            <div className="wf2-orderPanelHeader">
              <h3 className="wf2-orderPanelTitle">Movie Ticket</h3>
              <span className="wf2-orderChip">1 Ticket</span>
            </div>
            <div className="wf2-orderMovieRow">
              <div className="wf2-orderPoster">
                <img src={order.movie.poster || gharjwai} alt={order.movie.title} />
              </div>
              <div className="wf2-orderMovieInfo">
                <div className="wf2-orderMovieTitle">{order.movie.title}</div>
                <div className="wf2-orderMovieMeta">
                  Language: {order.movie.language} | {order.movie.runtime}
                </div>
                <div className="wf2-orderMovieMeta">{order.movie.seat}</div>
                <div className="wf2-orderMovieMeta">{order.movie.venue}</div>
              </div>
              <div className="wf2-orderPriceTag">{formatPrice(order.ticketTotal)}</div>
            </div>
          </section>

          <section className="wf2-orderPanel">
            <div className="wf2-orderPanelHeader">
              <h3 className="wf2-orderPanelTitle">Food & Beverage</h3>
              <span className="wf2-orderChip">{foodCount} Items</span>
            </div>
            {order.items.length ? (
              <div className="wf2-orderItemList">
                {order.items.map((item) => (
                  <div className="wf2-orderItemRow" key={item.id}>
                    <div className="wf2-orderItemInfo">
                      <div className="wf2-orderItemName">{item.name}</div>
                      <div className="wf2-orderItemMeta">{item.desc}</div>
                    </div>
                    <div className="wf2-orderItemQty">{item.qty}</div>
                    <div className="wf2-orderItemPrice">{formatPrice(item.price)}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="wf2-orderEmpty">No food items added.</div>
            )}
          </section>
        </div>

        <aside className="wf2-orderSidebar">
          <section className="wf2-orderPanel">
            <div className="wf2-orderPanelHeader">
              <h3 className="wf2-orderPanelTitle">Order Summary</h3>
            </div>
            <div className="wf2-orderSummaryRow">
              <span>Ticket Total</span>
              <span>{formatPrice(order.ticketTotal)}</span>
            </div>
            <div className="wf2-orderSummaryRow">
              <span>Food Subtotal</span>
              <span>{formatPrice(foodTotal)}</span>
            </div>
            <div className="wf2-orderSummaryRow">
              <span>Convenience Fee</span>
              <span>{formatPrice(0)}</span>
            </div>
            <div className="wf2-orderSummaryTotal">
              <span>Grand Total</span>
              <span>{formatPrice(orderTotal)}</span>
            </div>
            <button
              className="wf2-orderPayBtn"
              type="button"
              onClick={handlePayNow}
              disabled={isPaying}
            >
              {isPaying ? "Processing..." : "Pay Now"}
            </button>
            {payError ? <div className="wf2-orderQrError">{payError}</div> : null}
          </section>
        </aside>
      </div>
    </div>
  );
}

function extractSeatsFromLabel(value) {
  if (!value) return [];
  const text = String(value);
  const matches = text.match(/[A-Za-z]+\s*\d+/g);
  if (!matches) return [];
  return matches.map((item) => item.replace(/\s+/g, "").toUpperCase());
}

function getStoredUser() {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("user");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}
