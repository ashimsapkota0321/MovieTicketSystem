import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import "../css/orderConfirm.css";
import gharjwai from "../images/gharjwai.jpg";
import {
  applyBookingCoupon,
  fetchActiveSubscription,
  fetchLoyaltyRewards,
  fetchReferralDashboard,
  fetchUserWallet,
  payBookingWithUserWallet,
  previewLoyaltyCheckout,
  previewSubscriptionCheckout,
  previewReferralWalletCheckout,
  releaseBookingSeats,
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
  const [loadingLoyalty, setLoadingLoyalty] = useState(false);
  const [applyingLoyalty, setApplyingLoyalty] = useState(false);
  const [loyaltyWallet, setLoyaltyWallet] = useState(null);
  const [availableRewards, setAvailableRewards] = useState([]);
  const [selectedRewardId, setSelectedRewardId] = useState("");
  const [pointsToRedeem, setPointsToRedeem] = useState("");
  const [loyaltyPreview, setLoyaltyPreview] = useState(null);
  const [loyaltyError, setLoyaltyError] = useState("");
  const [loadingReferralWallet, setLoadingReferralWallet] = useState(false);
  const [previewingReferralWallet, setPreviewingReferralWallet] = useState(false);
  const [referralWallet, setReferralWallet] = useState(null);
  const [useReferralWallet, setUseReferralWallet] = useState(false);
  const [requestedReferralWalletAmount, setRequestedReferralWalletAmount] = useState("");
  const [referralWalletPreview, setReferralWalletPreview] = useState(null);
  const [referralWalletError, setReferralWalletError] = useState("");
  const [loadingSubscription, setLoadingSubscription] = useState(false);
  const [previewingSubscription, setPreviewingSubscription] = useState(false);
  const [activeSubscription, setActiveSubscription] = useState(null);
  const [useSubscription, setUseSubscription] = useState(false);
  const [useSubscriptionFreeTicket, setUseSubscriptionFreeTicket] = useState(false);
  const [requestedSubscriptionFreeTickets, setRequestedSubscriptionFreeTickets] = useState("1");
  const [subscriptionPreview, setSubscriptionPreview] = useState(null);
  const [subscriptionError, setSubscriptionError] = useState("");

  const foodTotal = order.items.reduce((sum, item) => sum + item.price * item.qty, 0);
  const foodCount = order.items.reduce((sum, item) => sum + (item.qty || 0), 0);
  const couponDiscount = Number(couponResult?.discount_amount || 0);
  const loyaltyDiscount = Number(loyaltyPreview?.total_discount || 0);
  const couponAdjustedSubtotal = Math.max(Number(order.ticketTotal || 0) - couponDiscount, 0);
  const loyaltyAdjustedSubtotal = Math.max(couponAdjustedSubtotal - loyaltyDiscount, 0);
  const subscriptionDiscount = Number(subscriptionPreview?.total_discount || 0);
  const referralSubtotal = Math.max(loyaltyAdjustedSubtotal - subscriptionDiscount, 0);
  const referralWalletDiscount = Number(referralWalletPreview?.applied_amount || 0);
  const ticketPayable = Math.max(referralSubtotal - referralWalletDiscount, 0);
  const orderTotal = ticketPayable + foodTotal;
  const formatPrice = (value) => `Npr ${value}`;
  const [isPaying, setIsPaying] = useState(false);
  const [isPayingWithWallet, setIsPayingWithWallet] = useState(false);
  const [loadingCashWallet, setLoadingCashWallet] = useState(false);
  const [cashWallet, setCashWallet] = useState(null);
  const [paymentError, setPaymentError] = useState("");
  const cashWalletBalance = Number(cashWallet?.balance || 0);
  const walletCanCoverTotal = cashWalletBalance >= orderTotal;
  const skipResumeNoticeOnUnmountRef = useRef(false);
  const loyaltyVendorId = Number(order?.bookingContext?.cinemaId || order?.movie?.cinemaId || 0) || null;

  useEffect(() => {
    let active = true;

    const loadLoyaltyAndReferral = async () => {
      setLoadingLoyalty(true);
      setLoadingReferralWallet(true);
      setLoadingSubscription(true);
      setLoadingCashWallet(true);
      try {
        const [loyaltyData, referralData, subscriptionData, walletData] = await Promise.all([
          fetchLoyaltyRewards(loyaltyVendorId ? { vendor_id: loyaltyVendorId } : {}),
          fetchReferralDashboard(),
          fetchActiveSubscription(loyaltyVendorId ? { vendor_id: loyaltyVendorId } : {}),
          fetchUserWallet(),
        ]);
        if (!active) return;
        setLoyaltyWallet(loyaltyData?.wallet || null);
        setAvailableRewards(Array.isArray(loyaltyData?.rewards) ? loyaltyData.rewards : []);
        setReferralWallet(referralData?.wallet || null);
        setActiveSubscription(subscriptionData?.subscription || null);
        setCashWallet(walletData?.cash_wallet || null);
      } catch {
        if (!active) return;
        setLoyaltyWallet(null);
        setAvailableRewards([]);
        setReferralWallet(null);
        setActiveSubscription(null);
        setCashWallet(null);
      } finally {
        if (active) setLoadingLoyalty(false);
        if (active) setLoadingReferralWallet(false);
        if (active) setLoadingSubscription(false);
        if (active) setLoadingCashWallet(false);
      }
    };

    loadLoyaltyAndReferral();
    return () => {
      active = false;
    };
  }, [loyaltyVendorId]);

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
      releaseBookingSeats({
        ...payload,
        track_dropoff: true,
        dropoff_stage: "BOOKING",
        dropoff_reason: "LEFT_BOOKING_PROCESS",
      }).catch(() => {});
    };
  }, [order]);

  const buildCheckoutOrder = (selectedPaymentMethod = "ESEWA") => {
    const priceLockToken =
      order?.pricing?.price_lock_token ||
      order?.pricing?.priceLockToken ||
      order?.bookingContext?.priceLockToken ||
      order?.bookingContext?.price_lock_token ||
      null;

    return {
      movie: order.movie,
      ticketTotal: ticketPayable,
      originalTicketTotal: Number(order.ticketTotal || 0),
      couponCode: couponResult?.coupon?.code || null,
      coupon: couponResult?.coupon || null,
      discountAmount: couponDiscount,
      items: order.items,
      foodTotal,
      total: orderTotal,
      payment_method: selectedPaymentMethod,
      paymentMethod: selectedPaymentMethod,
      reward_id: selectedRewardId ? Number(selectedRewardId) : null,
      loyalty_points_to_redeem: Number(pointsToRedeem || 0),
      loyalty_discount_amount: loyaltyDiscount,
      use_subscription: Boolean(useSubscription),
      user_subscription_id: useSubscription
        ? Number(subscriptionPreview?.user_subscription_id || activeSubscription?.id || 0) || null
        : null,
      use_subscription_free_ticket: Boolean(useSubscription && useSubscriptionFreeTicket),
      subscription_free_tickets: useSubscription
        ? Math.max(Number(requestedSubscriptionFreeTickets || 0), 0)
        : 0,
      subscription_discount_amount: subscriptionDiscount,
      use_referral_wallet: Boolean(useReferralWallet && referralWalletDiscount > 0),
      referral_wallet_amount: useReferralWallet ? referralWalletDiscount : 0,
      referral_wallet: {
        enabled: Boolean(useReferralWallet),
        requested_amount: Number(requestedReferralWalletAmount || 0),
        applied_amount: useReferralWallet ? referralWalletDiscount : 0,
        preview: referralWalletPreview || null,
      },
      subscription: {
        enabled: Boolean(useSubscription),
        user_subscription_id: useSubscription
          ? Number(subscriptionPreview?.user_subscription_id || activeSubscription?.id || 0) || null
          : null,
        use_free_ticket: Boolean(useSubscription && useSubscriptionFreeTicket),
        requested_free_tickets: useSubscription
          ? Math.max(Number(requestedSubscriptionFreeTickets || 0), 0)
          : 0,
        preview: subscriptionPreview || null,
      },
      loyalty: {
        reward_id: selectedRewardId ? Number(selectedRewardId) : null,
        points_to_redeem: Number(pointsToRedeem || 0),
        preview: loyaltyPreview || null,
      },
      selectedSeats: order.selectedSeats,
      price_lock_token: priceLockToken,
      strict_price_lock: Boolean(priceLockToken),
      pricing: order?.pricing || null,
      bookingContext: {
        ...(order.bookingContext || {}),
        user_id: order?.bookingContext?.user_id || state?.user?.id || null,
        priceLockToken: priceLockToken,
        price_lock_token: priceLockToken,
        date:
          order?.bookingContext?.date ||
          order?.bookingContext?.showDate ||
          order?.movie?.showDate ||
          state?.movie?.showDate ||
          null,
        time:
          order?.bookingContext?.time ||
          order?.bookingContext?.showTime ||
          order?.movie?.showTime ||
          state?.movie?.showTime ||
          null,
        showDate:
          order?.bookingContext?.showDate ||
          order?.bookingContext?.date ||
          order?.movie?.showDate ||
          state?.movie?.showDate ||
          null,
        showTime:
          order?.bookingContext?.showTime ||
          order?.bookingContext?.time ||
          order?.movie?.showTime ||
          state?.movie?.showTime ||
          null,
      },
    };
  };

  const applySubscriptionPreview = async () => {
    if (!useSubscription) {
      setSubscriptionPreview(null);
      setSubscriptionError("");
      return {
        total_discount: 0,
        final_total: loyaltyAdjustedSubtotal,
      };
    }

    if (!activeSubscription?.id) {
      const error = new Error("No active membership found for this checkout.");
      setSubscriptionPreview(null);
      setSubscriptionError(error.message);
      throw error;
    }

    const subtotal = Math.max(loyaltyAdjustedSubtotal, 0);
    if (subtotal <= 0) {
      const zeroPreview = {
        user_subscription_id: activeSubscription.id,
        total_discount: 0,
        final_total: 0,
        free_tickets_to_use: 0,
      };
      setSubscriptionPreview(zeroPreview);
      setSubscriptionError("");
      return zeroPreview;
    }

    const requestedFreeTickets = Math.max(Number(requestedSubscriptionFreeTickets || 0), 0);
    if (!Number.isFinite(requestedFreeTickets)) {
      const error = new Error("Enter a valid free ticket count.");
      setSubscriptionPreview(null);
      setSubscriptionError(error.message);
      throw error;
    }

    setPreviewingSubscription(true);
    setSubscriptionError("");
    try {
      const preview = await previewSubscriptionCheckout({
        subtotal,
        vendor_id: loyaltyVendorId || undefined,
        user_subscription_id: Number(activeSubscription.id),
        seat_count: Math.max(Number(order?.selectedSeats?.length || 1), 1),
        use_free_ticket: Boolean(useSubscriptionFreeTicket),
        requested_free_tickets: requestedFreeTickets,
        coupon_applied: couponDiscount > 0,
        loyalty_applied: loyaltyDiscount > 0,
        referral_wallet_applied: false,
      });
      setSubscriptionPreview(preview || null);
      return preview || { total_discount: 0, final_total: subtotal, free_tickets_to_use: 0 };
    } catch (error) {
      setSubscriptionPreview(null);
      const message = error.message || "Unable to preview membership benefits.";
      setSubscriptionError(message);
      throw new Error(message);
    } finally {
      setPreviewingSubscription(false);
    }
  };

  const applyReferralWalletPreview = async () => {
    if (!useReferralWallet) {
      setReferralWalletPreview(null);
      setReferralWalletError("");
      return {
        applied_amount: 0,
        remaining_total: referralSubtotal,
      };
    }

    const subtotal = Math.max(referralSubtotal, 0);
    if (subtotal <= 0) {
      const zeroPreview = {
        subtotal,
        applied_amount: 0,
        remaining_total: 0,
        requested_amount: 0,
        max_usable_amount: 0,
      };
      setReferralWalletPreview(zeroPreview);
      setReferralWalletError("");
      return zeroPreview;
    }

    const normalizedRequested = String(requestedReferralWalletAmount || "").trim();
    const requestedAmount = normalizedRequested ? Number(normalizedRequested) : undefined;
    if (requestedAmount != null && (!Number.isFinite(requestedAmount) || requestedAmount < 0)) {
      const error = new Error("Enter a valid wallet amount.");
      setReferralWalletError(error.message);
      throw error;
    }

    setPreviewingReferralWallet(true);
    setReferralWalletError("");
    try {
      const preview = await previewReferralWalletCheckout({
        subtotal,
        use_referral_wallet: true,
        requested_amount: requestedAmount,
      });
      setReferralWalletPreview(preview || null);
      return preview || { applied_amount: 0, remaining_total: subtotal };
    } catch (error) {
      setReferralWalletPreview(null);
      const message = error.message || "Unable to preview referral wallet usage.";
      setReferralWalletError(message);
      throw new Error(message);
    } finally {
      setPreviewingReferralWallet(false);
    }
  };

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
      setLoyaltyPreview(null);
      setLoyaltyError("");
      setSubscriptionPreview(null);
      setSubscriptionError("");
      setReferralWalletPreview(null);
      setReferralWalletError("");
    } catch (error) {
      setCouponResult(null);
      setCouponError(error.message || "Unable to apply coupon.");
      setLoyaltyPreview(null);
      setSubscriptionPreview(null);
      setReferralWalletPreview(null);
    } finally {
      setApplyingCoupon(false);
    }
  };

  const handleApplyLoyalty = async () => {
    const rewardId = selectedRewardId ? Number(selectedRewardId) : null;
    const points = Math.max(Number(pointsToRedeem || 0), 0);
    if (!rewardId && points <= 0) {
      setLoyaltyError("Select a reward or enter points to redeem.");
      return;
    }

    setApplyingLoyalty(true);
    setLoyaltyError("");
    try {
      const preview = await previewLoyaltyCheckout({
        subtotal: couponAdjustedSubtotal,
        reward_id: rewardId || undefined,
        points_to_redeem: points,
        vendor_id: loyaltyVendorId || undefined,
      });
      setLoyaltyPreview(preview || null);
      if (preview?.reward?.id) {
        setSelectedRewardId(String(preview.reward.id));
      }
      if (preview?.direct_points_used != null) {
        setPointsToRedeem(String(preview.direct_points_used));
      }
      setSubscriptionPreview(null);
      setSubscriptionError("");
      setReferralWalletPreview(null);
      setReferralWalletError("");
    } catch (error) {
      setLoyaltyPreview(null);
      setLoyaltyError(error.message || "Unable to apply loyalty redemption.");
      setSubscriptionPreview(null);
      setReferralWalletPreview(null);
    } finally {
      setApplyingLoyalty(false);
    }
  };

  const handleClearLoyalty = () => {
    setSelectedRewardId("");
    setPointsToRedeem("");
    setLoyaltyPreview(null);
    setLoyaltyError("");
    setSubscriptionPreview(null);
    setSubscriptionError("");
    setReferralWalletPreview(null);
    setReferralWalletError("");
  };

  const handleApplyReferralWallet = async () => {
    try {
      if (useSubscription) {
        await applySubscriptionPreview();
      }
      await applyReferralWalletPreview();
    } catch {
      // Error state is already managed in applyReferralWalletPreview.
    }
  };

  const handlePayWithEsewa = async () => {
    if (isPaying || isPayingWithWallet || applyingCoupon || applyingLoyalty || previewingSubscription || previewingReferralWallet) return;
    setPaymentError("");
    if (useSubscription) {
      try {
        await applySubscriptionPreview();
      } catch {
        return;
      }
    }
    if (useReferralWallet) {
      try {
        await applyReferralWalletPreview();
      } catch {
        return;
      }
    }

    setIsPaying(true);
    skipResumeNoticeOnUnmountRef.current = true;
    const checkoutOrder = buildCheckoutOrder("ESEWA");
    navigate("/esewa/checkout", {
      state: {
        amount: orderTotal,
        order: checkoutOrder,
      },
    });
  };

  const handlePayWithWallet = async () => {
    if (isPaying || isPayingWithWallet || applyingCoupon || applyingLoyalty || previewingSubscription || previewingReferralWallet) return;
    setPaymentError("");
    if (!walletCanCoverTotal) {
      setPaymentError("Insufficient wallet balance. Add money to your wallet or choose eSewa.");
      return;
    }
    try {
      if (useSubscription) {
        await applySubscriptionPreview();
      }
      if (useReferralWallet) {
        await applyReferralWalletPreview();
      }
      setIsPayingWithWallet(true);
      const checkoutOrder = buildCheckoutOrder("USER_WALLET");
      const result = await payBookingWithUserWallet({
        order: checkoutOrder,
        amount: orderTotal,
      });
      const ticketPayload =
        result?.ticket && typeof result.ticket === "object"
          ? result.ticket
          : {
              reference: result?.reference || "",
              qr_code: result?.qr_code || "",
              ticket_image: result?.ticket_image || "",
              download_url: result?.download_url || "",
              details_url: result?.details_url || "",
            };
      if (result?.wallet && typeof result.wallet === "object") {
        setCashWallet(result.wallet);
      }
      skipResumeNoticeOnUnmountRef.current = true;
      navigate("/thank-you", {
        state: {
          order: checkoutOrder,
          ticket: ticketPayload,
        },
      });
    } catch (error) {
      setPaymentError(error?.message || "Unable to complete wallet payment.");
    } finally {
      setIsPayingWithWallet(false);
    }
  };

  const isPaymentActionBusy =
    isPaying ||
    isPayingWithWallet ||
    applyingCoupon ||
    applyingLoyalty ||
    previewingSubscription ||
    previewingReferralWallet;

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
              <span>Loyalty Points</span>
              <span>
                {loadingLoyalty
                  ? "Loading..."
                  : Number(loyaltyWallet?.available_points || 0).toLocaleString()}
              </span>
            </div>
            <div className="wf2-orderSummaryRow" style={{ gap: 10 }}>
              <span style={{ flex: 1 }}>Reward</span>
              <select
                className="form-select"
                value={selectedRewardId}
                onChange={(event) => {
                  setSelectedRewardId(event.target.value);
                  setLoyaltyPreview(null);
                  setLoyaltyError("");
                }}
                style={{ maxWidth: 220 }}
              >
                <option value="">No reward</option>
                {availableRewards.map((reward) => (
                  <option key={reward.id} value={reward.id}>
                    {reward.title} ({reward.points_required} pts)
                  </option>
                ))}
              </select>
            </div>
            <div className="wf2-orderSummaryRow" style={{ gap: 10 }}>
              <span style={{ flex: 1 }}>Redeem Points</span>
              <input
                type="number"
                className="form-control"
                value={pointsToRedeem}
                min="0"
                onChange={(event) => {
                  setPointsToRedeem(event.target.value);
                  setLoyaltyPreview(null);
                  setLoyaltyError("");
                }}
                placeholder="0"
                style={{ maxWidth: 120 }}
              />
              <button
                type="button"
                className="btn btn-outline-light btn-sm"
                onClick={handleApplyLoyalty}
                disabled={applyingLoyalty}
              >
                {applyingLoyalty ? "Applying..." : "Apply"}
              </button>
            </div>
            {loyaltyError ? <div className="text-danger small mb-2">{loyaltyError}</div> : null}
            {loyaltyDiscount > 0 ? (
              <div className="wf2-orderSummaryRow text-success">
                <span>Loyalty Discount</span>
                <span>-{formatPrice(loyaltyDiscount)}</span>
              </div>
            ) : null}
            {loyaltyPreview ? (
              <div className="small mb-2" style={{ color: "#d0f0d0" }}>
                {Number(loyaltyPreview?.total_points_to_use || 0)} points will be used.
                <button
                  type="button"
                  className="btn btn-link btn-sm"
                  style={{ color: "#d0f0d0", textDecoration: "underline" }}
                  onClick={handleClearLoyalty}
                >
                  Remove
                </button>
              </div>
            ) : null}
            <div className="wf2-orderSummaryRow">
              <span>Membership</span>
              <span>
                {loadingSubscription
                  ? "Loading..."
                  : activeSubscription?.plan_name || "Not active"}
              </span>
            </div>
            <div className="wf2-orderSummaryRow" style={{ alignItems: "center" }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, margin: 0 }}>
                <input
                  type="checkbox"
                  checked={useSubscription}
                  disabled={loadingSubscription || previewingSubscription || !activeSubscription?.id}
                  onChange={(event) => {
                    const enabled = event.target.checked;
                    setUseSubscription(enabled);
                    setSubscriptionError("");
                    setReferralWalletPreview(null);
                    setReferralWalletError("");
                    if (!enabled) {
                      setSubscriptionPreview(null);
                      return;
                    }
                    setSubscriptionPreview(null);
                  }}
                />
                <span>Use membership benefits</span>
              </label>
            </div>
            {useSubscription ? (
              <>
                <div className="wf2-orderSummaryRow" style={{ alignItems: "center" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, margin: 0 }}>
                    <input
                      type="checkbox"
                      checked={useSubscriptionFreeTicket}
                      disabled={previewingSubscription}
                      onChange={(event) => {
                        setUseSubscriptionFreeTicket(event.target.checked);
                        setSubscriptionPreview(null);
                        setSubscriptionError("");
                        setReferralWalletPreview(null);
                        setReferralWalletError("");
                      }}
                    />
                    <span>Use free tickets</span>
                  </label>
                </div>
                <div className="wf2-orderSummaryRow" style={{ gap: 10 }}>
                  <span style={{ flex: 1 }}>Free Tickets</span>
                  <input
                    type="number"
                    min="0"
                    className="form-control"
                    value={requestedSubscriptionFreeTickets}
                    onChange={(event) => {
                      setRequestedSubscriptionFreeTickets(event.target.value);
                      setSubscriptionPreview(null);
                      setSubscriptionError("");
                      setReferralWalletPreview(null);
                      setReferralWalletError("");
                    }}
                    placeholder="1"
                    style={{ maxWidth: 120 }}
                  />
                  <button
                    type="button"
                    className="btn btn-outline-light btn-sm"
                    onClick={async () => {
                      try {
                        await applySubscriptionPreview();
                      } catch {
                        // Error state is already managed in applySubscriptionPreview.
                      }
                    }}
                    disabled={previewingSubscription}
                  >
                    {previewingSubscription ? "Checking..." : "Preview"}
                  </button>
                </div>
                {subscriptionError ? (
                  <div className="text-danger small mb-2">{subscriptionError}</div>
                ) : null}
                {subscriptionPreview ? (
                  <div className="small mb-2" style={{ color: "#d0f0d0" }}>
                    Free tickets to use: {Number(subscriptionPreview?.free_tickets_to_use || 0)} | Remaining after checkout: {Number(subscriptionPreview?.remaining_free_tickets_after || 0)}
                  </div>
                ) : null}
              </>
            ) : null}
            {subscriptionDiscount > 0 ? (
              <div className="wf2-orderSummaryRow text-success">
                <span>Membership Discount</span>
                <span>-{formatPrice(subscriptionDiscount)}</span>
              </div>
            ) : null}
            <div className="wf2-orderSummaryRow">
              <span>Referral Wallet</span>
              <span>
                {loadingReferralWallet
                  ? "Loading..."
                  : `NPR ${Number(referralWallet?.spendable_balance || 0).toLocaleString()}`}
              </span>
            </div>
            <div className="wf2-orderSummaryRow" style={{ alignItems: "center" }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, margin: 0 }}>
                <input
                  type="checkbox"
                  checked={useReferralWallet}
                  disabled={loadingReferralWallet || previewingReferralWallet}
                  onChange={(event) => {
                    const enabled = event.target.checked;
                    setUseReferralWallet(enabled);
                    setReferralWalletError("");
                    if (!enabled) {
                      setReferralWalletPreview(null);
                      return;
                    }
                    setReferralWalletPreview(null);
                  }}
                />
                <span>Use referral wallet credit</span>
              </label>
            </div>
            {useReferralWallet ? (
              <>
                <div className="wf2-orderSummaryRow" style={{ gap: 10 }}>
                  <span style={{ flex: 1 }}>Wallet Amount</span>
                  <input
                    type="number"
                    min="0"
                    className="form-control"
                    value={requestedReferralWalletAmount}
                    onChange={(event) => {
                      setRequestedReferralWalletAmount(event.target.value);
                      setReferralWalletPreview(null);
                      setReferralWalletError("");
                    }}
                    placeholder="Auto"
                    style={{ maxWidth: 120 }}
                  />
                  <button
                    type="button"
                    className="btn btn-outline-light btn-sm"
                    onClick={handleApplyReferralWallet}
                    disabled={previewingReferralWallet}
                  >
                    {previewingReferralWallet ? "Checking..." : "Preview"}
                  </button>
                </div>
                {referralWalletError ? (
                  <div className="text-danger small mb-2">{referralWalletError}</div>
                ) : null}
                {referralWalletPreview ? (
                  <div className="small mb-2" style={{ color: "#d0f0d0" }}>
                    Max usable now: NPR {Number(referralWalletPreview?.max_usable_amount || 0).toLocaleString()} ({Number(referralWalletPreview?.cap_percent || 0).toLocaleString()}% cap).
                  </div>
                ) : null}
              </>
            ) : null}
            {referralWalletDiscount > 0 ? (
              <div className="wf2-orderSummaryRow text-success">
                <span>Referral Wallet Discount</span>
                <span>-{formatPrice(referralWalletDiscount)}</span>
              </div>
            ) : null}
            <div className="wf2-orderSummaryRow">
              <span>Mero Wallet</span>
              <span>
                {loadingCashWallet
                  ? "Loading..."
                  : `NPR ${cashWalletBalance.toLocaleString()}`}
              </span>
            </div>
            {!walletCanCoverTotal ? (
              <div className="text-danger small mb-2">
                Insufficient wallet balance. Add money to your wallet or choose eSewa.
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
            <div className="wf2-orderPaymentActions">
              <button
                className="wf2-orderPayBtn"
                type="button"
                onClick={handlePayWithEsewa}
                disabled={isPaymentActionBusy}
              >
                {isPaying ? "Redirecting..." : "Pay with eSewa"}
              </button>
              <button
                className="wf2-orderWalletPayBtn"
                type="button"
                onClick={handlePayWithWallet}
                disabled={isPaymentActionBusy || loadingCashWallet || !walletCanCoverTotal}
              >
                {isPayingWithWallet ? "Processing payment..." : "Pay with Mero Wallet"}
              </button>
            </div>
            {paymentError ? <div className="wf2-orderQrError">{paymentError}</div> : null}
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
