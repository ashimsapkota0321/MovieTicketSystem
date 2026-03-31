import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import "../css/orderConfirm.css";
import gharjwai from "../images/gharjwai.jpg";
import {
  applyBookingCoupon,
  createBookingResumeNotification,
  createTestBookingSuccess,
} from "../lib/catalogApi";

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

export default function OrderConfirm() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location?.state || {};

  const order = useMemo(() => {
    const hasBookingPayload = Boolean(
      state.movie || state.ticketTotal || state.selectedSeats || state.bookingContext
    );
    const items = Array.isArray(state.items)
      ? state.items
      : hasBookingPayload
        ? []
        : DEFAULT_ORDER.items;
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

  const [couponCode, setCouponCode] = useState(
    String(state?.coupon?.code || state?.couponCode || "").toUpperCase()
  );
  const [couponResult, setCouponResult] = useState(
    state?.coupon && state?.discountAmount != null
      ? {
          coupon: state.coupon,
          discount_amount: Number(state.discountAmount || 0),
          final_total: Number(state.ticketTotal || 0),
        }
      : null
  );
  const [couponError, setCouponError] = useState("");
  const [applyingCoupon, setApplyingCoupon] = useState(false);

  const foodTotal = order.items.reduce((sum, item) => sum + item.price * item.qty, 0);
  const foodCount = order.items.reduce((sum, item) => sum + (item.qty || 0), 0);
  const couponDiscount = Number(couponResult?.discount_amount || 0);
  const ticketPayable = Math.max(Number(order.ticketTotal || 0) - couponDiscount, 0);
  const orderTotal = ticketPayable + foodTotal;
  const formatPrice = (value) => `Npr ${value}`;
  const [isPaying, setIsPaying] = useState(false);
  const [isCreatingTestBooking, setIsCreatingTestBooking] = useState(false);
  const [testBookingError, setTestBookingError] = useState("");
  const skipResumeNoticeOnUnmountRef = useRef(false);

  useEffect(() => {
    return () => {
      if (skipResumeNoticeOnUnmountRef.current) return;
      const selectedSeats = Array.isArray(order.selectedSeats) ? order.selectedSeats : [];
      if (!selectedSeats.length) return;

      const context = order?.bookingContext || {};
      const payload = {
        movie_id: context.movieId || context.movie_id || order?.movie?.movieId,
        cinema_id: context.cinemaId || context.cinema_id || order?.movie?.cinemaId,
        show_id: context.showId || context.show_id,
        date: context.date || context.showDate || order?.movie?.showDate,
        time: context.time || context.showTime || order?.movie?.showTime,
        hall: context.hall || order?.movie?.hall,
        selected_seats: selectedSeats,
      };
      createBookingResumeNotification(payload).catch(() => {});
    };
  }, [order]);

  const buildCheckoutOrder = () => ({
    movie: order.movie,
    ticketTotal: ticketPayable,
    originalTicketTotal: Number(order.ticketTotal || 0),
    couponCode: couponResult?.coupon?.code || null,
    coupon: couponResult?.coupon || null,
    discountAmount: couponDiscount,
    items: order.items,
    foodTotal,
    total: orderTotal,
    selectedSeats: order.selectedSeats,
    bookingContext: order.bookingContext,
  });

  const handleApplyCoupon = async () => {
    const normalizedCode = String(couponCode || "").trim().toUpperCase();
    if (!normalizedCode) {
      setCouponError("Enter a coupon code.");
      return;
    }

    setApplyingCoupon(true);
    setCouponError("");
    try {
      const payload = {
        coupon_code: normalizedCode,
        ticket_total: Number(order.ticketTotal || 0),
        booking: {
          movie_id: order?.bookingContext?.movieId,
          cinema_id: order?.bookingContext?.cinemaId,
          show_id: order?.bookingContext?.showId,
          date: order?.bookingContext?.date,
          time: order?.bookingContext?.time,
          hall: order?.bookingContext?.hall,
          selected_seats: order?.selectedSeats || order?.bookingContext?.selectedSeats || [],
        },
      };
      const result = await applyBookingCoupon(payload);
      setCouponResult(result || null);
      setCouponCode(String(result?.coupon?.code || normalizedCode));
    } catch (error) {
      setCouponResult(null);
      setCouponError(error.message || "Unable to apply coupon.");
    } finally {
      setApplyingCoupon(false);
    }
  };

  const handlePayWithEsewa = () => {
    if (isPaying || isCreatingTestBooking) return;
    setIsPaying(true);
    skipResumeNoticeOnUnmountRef.current = true;
    const checkoutOrder = buildCheckoutOrder();
    navigate("/esewa/checkout", {
      state: {
        amount: orderTotal,
        order: checkoutOrder,
      },
    });
  };

  const handleTestBookingSuccess = async () => {
    if (isPaying || isCreatingTestBooking) return;
    const selectedSeats = Array.isArray(order.selectedSeats) ? order.selectedSeats : [];
    const context = order?.bookingContext || {};
    const hasShowContext = Boolean(
      context?.showId || (context?.movieId && context?.cinemaId && context?.date && context?.time)
    );
    if (!selectedSeats.length || !hasShowContext) {
      setTestBookingError("Select a valid show and seats before test booking.");
      return;
    }

    setTestBookingError("");
    setIsCreatingTestBooking(true);
    try {
      skipResumeNoticeOnUnmountRef.current = true;
      const checkoutOrder = buildCheckoutOrder();
      const result = await createTestBookingSuccess({ order: checkoutOrder });
      navigate("/thank-you", {
        state: {
          order: checkoutOrder,
          ticket: {
            reference: result?.reference || "",
            qr_code: result?.qr_code || "",
            ticket_image: result?.ticket_image || "",
            download_url: result?.download_url || "",
            details_url: result?.details_url || "",
          },
        },
      });
    } catch (error) {
      setTestBookingError(error?.message || "Unable to create test booking.");
    } finally {
      setIsCreatingTestBooking(false);
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
            <div className="wf2-orderSummaryRow" style={{ gap: 10 }}>
              <span style={{ flex: 1 }}>Coupon</span>
              <input
                type="text"
                className="form-control"
                value={couponCode}
                onChange={(event) => {
                  setCouponCode(event.target.value.toUpperCase());
                  setCouponError("");
                }}
                placeholder="ENTER CODE"
                style={{ maxWidth: 180 }}
              />
              <button
                type="button"
                className="btn btn-outline-light btn-sm"
                onClick={handleApplyCoupon}
                disabled={applyingCoupon}
              >
                {applyingCoupon ? "Applying..." : "Apply"}
              </button>
            </div>
            {couponError ? <div className="text-danger small mb-2">{couponError}</div> : null}
            {couponResult?.coupon?.code ? (
              <div className="wf2-orderSummaryRow text-success">
                <span>Discount ({couponResult.coupon.code})</span>
                <span>-{formatPrice(couponDiscount)}</span>
              </div>
            ) : null}
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
              onClick={handlePayWithEsewa}
              disabled={isPaying || isCreatingTestBooking}
            >
              {isPaying ? "Redirecting..." : "Pay with eSewa"}
            </button>
            <button
              className="wf2-orderGhostBtn"
              type="button"
              onClick={handleTestBookingSuccess}
              disabled={isPaying || isCreatingTestBooking}
            >
              {isCreatingTestBooking ? "Creating booking..." : "Test Booking Success"}
            </button>
            {testBookingError ? <div className="wf2-orderQrError">{testBookingError}</div> : null}
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
