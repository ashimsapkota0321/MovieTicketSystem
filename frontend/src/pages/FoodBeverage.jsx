import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, Search, Plus, Minus } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import "../css/foodBeverage.css";
import gharjwai from "../images/gharjwai.jpg";
import { fetchFoodItemsByVendor, releaseBookingSeats } from "../lib/catalogApi";

const CATEGORIES_BASE = ["All"];

const TICKET_PRICE = 300;
const DEFAULT_MOVIE = {
  title: "Hami Teen Bhai",
  language: "Nepali",
  runtime: "2h 10m",
  seat: "Seat No: A12, A13",
  venue: "QFX Civil Mall, 18 Feb 2026, 08:30 PM",
  poster: gharjwai,
};

export default function FoodBeverage() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location?.state || {};
  const skipReleaseOnUnmountRef = useRef(false);
  const [activeCategory, setActiveCategory] = useState("All");
  const [query, setQuery] = useState("");
  const [cart, setCart] = useState({});
  const [foodItems, setFoodItems] = useState([]);
  const [loadingItems, setLoadingItems] = useState(true);

  const categories = useMemo(() => {
    const dynamic = Array.from(new Set(foodItems.map((item) => item.category).filter(Boolean)));
    return [...CATEGORIES_BASE, ...dynamic];
  }, [foodItems]);

  const filteredItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return foodItems.filter((item) => {
      const matchesCategory = activeCategory === "All" || item.category === activeCategory;
      const matchesQuery =
        !normalizedQuery ||
        item.name.toLowerCase().includes(normalizedQuery) ||
        item.desc.toLowerCase().includes(normalizedQuery);
      return matchesCategory && matchesQuery;
    });
  }, [activeCategory, query, foodItems]);

  const cartItems = useMemo(
    () => foodItems.filter((item) => cart[item.id]),
    [cart, foodItems]
  );

  const cartCount = cartItems.reduce((sum, item) => sum + cart[item.id], 0);
  const cartTotal = cartItems.reduce((sum, item) => sum + item.price * cart[item.id], 0);
  const ticketTotal = Number(state.ticketTotal) || TICKET_PRICE;
  const orderTotal = ticketTotal + cartTotal;
  const selectedSeats = Array.isArray(state.selectedSeats) ? state.selectedSeats : [];
  const orderMovie = {
    ...DEFAULT_MOVIE,
    ...(state.movie || {}),
    seat:
      state?.movie?.seat ||
      (selectedSeats.length ? `Seat No: ${selectedSeats.join(", ")}` : DEFAULT_MOVIE.seat),
    poster: state?.movie?.poster || DEFAULT_MOVIE.poster,
  };
  const bookingContext = state.bookingContext || {};

  useEffect(() => {
    return () => {
      if (skipReleaseOnUnmountRef.current) return;
      if (!selectedSeats.length) return;

      const payload = {
        movie_id: bookingContext.movieId || bookingContext.movie_id || state?.movie?.movieId,
        cinema_id: bookingContext.cinemaId || bookingContext.cinema_id || state?.movie?.cinemaId,
        show_id: bookingContext.showId || bookingContext.show_id,
        date: bookingContext.date || bookingContext.showDate || state?.movie?.showDate,
        time: bookingContext.time || bookingContext.showTime || state?.movie?.showTime,
        hall: bookingContext.hall || state?.movie?.hall,
        selected_seats: selectedSeats,
        track_dropoff: true,
        dropoff_stage: "BOOKING",
        dropoff_reason: "LEFT_BOOKING_PROCESS",
      };
      releaseBookingSeats(payload).catch(() => {});
    };
  }, [bookingContext, selectedSeats, state?.movie]);

  useEffect(() => {
    let mounted = true;
    const loadItems = async () => {
      const vendorId = bookingContext?.cinemaId || state?.movie?.cinemaId;
      if (!vendorId) {
        if (mounted) {
          setFoodItems([]);
          setLoadingItems(false);
          goToOrderConfirm([]);
        }
        return;
      }
      setLoadingItems(true);
      try {
        const items = await fetchFoodItemsByVendor({
          vendorId,
          hall: bookingContext?.hall || state?.movie?.hall || "",
        });
        if (!mounted) return;
        const normalized = (Array.isArray(items) ? items : []).map((item) => ({
          id: String(item.id),
          name: item.itemName,
          desc: item.category ? `Category: ${item.category}` : "Food Item",
          price: Number(item.price || 0),
          category: item.category || "Other",
          tag: item.hall ? `Hall ${item.hall}` : "",
          color: "linear-gradient(135deg, #f59e0b, #f6d35e)",
          image: "",
          isVeg: true,
        }));
        setFoodItems(normalized);

        if (normalized.length === 0) {
          goToOrderConfirm([]);
        }
      } catch {
        if (!mounted) return;
        setFoodItems([]);
        goToOrderConfirm([]);
      } finally {
        if (mounted) setLoadingItems(false);
      }
    };

    loadItems();
    return () => {
      mounted = false;
    };
  }, [bookingContext?.cinemaId, bookingContext?.hall]);

  const addItem = (id) => {
    setCart((prev) => ({ ...prev, [id]: (prev[id] || 0) + 1 }));
  };

  const removeItem = (id) => {
    setCart((prev) => {
      if (!prev[id]) return prev;
      const next = { ...prev };
      if (next[id] <= 1) {
        delete next[id];
      } else {
        next[id] -= 1;
      }
      return next;
    });
  };

  const formatPrice = (value) => `Npr ${value}`;
  const discountLabel = (item) => {
    if (!item.originalPrice || item.originalPrice <= item.price) return "";
    const percent = Math.round(((item.originalPrice - item.price) / item.originalPrice) * 100);
    return percent > 0 ? `${percent}% OFF` : "";
  };
  const buildOrderItems = () =>
    cartItems.map((item) => ({
      id: item.id,
      name: item.name,
      desc: item.desc,
      price: item.price,
      qty: cart[item.id],
    }));

  const goToOrderConfirm = (items) => {
    skipReleaseOnUnmountRef.current = true;
    navigate("/order-confirm", {
      state: {
        movie: orderMovie,
        ticketTotal,
        items,
        selectedSeats,
        bookingContext: {
          ...bookingContext,
          selectedSeats:
            bookingContext?.selectedSeats && Array.isArray(bookingContext.selectedSeats)
              ? bookingContext.selectedSeats
              : selectedSeats,
        },
      },
    });
  };

  return (
    <div className="wf2-page wf2-foodPage">
      <section className="wf2-foodHeader">
        <button
          className="wf2-foodBackBtn"
          type="button"
          onClick={() => navigate(-1)}
          aria-label="Go back"
        >
          <ChevronLeft size={18} />
        </button>
        <div className="wf2-foodHeaderInfo">
          <h2 className="wf2-foodHeaderTitle">
            {orderMovie.title} ({orderMovie.language || "Nepali"})
          </h2>
          <p className="wf2-foodHeaderSub">
            {orderMovie.venue || DEFAULT_MOVIE.venue}
          </p>
        </div>
        <div className="wf2-foodHeaderSpacer" />
        <button
          className="wf2-foodSkipBtn"
          type="button"
          onClick={() => goToOrderConfirm([])}
        >
          Skip
        </button>
      </section>

      <div className="wf2-foodLayout">
        <div className="wf2-foodPanel">
          <div className="wf2-foodToolbar">
            <h3 className="wf2-foodTitle">Grab a Bite!</h3>
            <div className="wf2-foodSearch">
              <Search size={16} />
              <input
                type="text"
                placeholder="Search for food items"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                aria-label="Search food items"
              />
            </div>
          </div>

          <div className="wf2-foodTabs">
            {categories.map((category) => (
              <button
                key={category}
                type="button"
                className={`wf2-foodTab ${activeCategory === category ? "wf2-foodTabActive" : ""}`}
                onClick={() => setActiveCategory(category)}
              >
                {category}
              </button>
            ))}
          </div>

          <div className="wf2-foodGrid">
            {loadingItems ? <div className="wf2-foodEmpty">Loading food items...</div> : null}
            {filteredItems.map((item) => {
              const qty = cart[item.id] || 0;
              const discount = discountLabel(item);
              const thumbStyle = item.image
                ? { background: "#ffffff" }
                : { background: item.color };
              return (
                <div className="wf2-foodItemCard" key={item.id}>
                  <span
                    className={`wf2-foodDietIcon ${
                      item.isVeg ? "wf2-foodDietIconVeg" : "wf2-foodDietIconNonVeg"
                    }`}
                    aria-hidden="true"
                  />
                  <div className="wf2-foodThumb" style={thumbStyle}>
                    {item.image ? (
                      <img src={item.image} alt={item.name} loading="lazy" />
                    ) : null}
                  </div>
                  <div className="wf2-foodItemBody">
                    {item.tag ? <span className="wf2-foodTag">{item.tag}</span> : null}
                    <h4 className="wf2-foodItemName">{item.name}</h4>
                    <p className="wf2-foodItemDesc">{item.desc}</p>
                    <div className="wf2-foodItemFooter">
                      <div className="wf2-foodItemPriceRow">
                        <span className="wf2-foodItemPrice">{formatPrice(item.price)}</span>
                        {item.originalPrice ? (
                          <span className="wf2-foodItemPriceOld">
                            {formatPrice(item.originalPrice)}
                          </span>
                        ) : null}
                        {discount ? (
                          <span className="wf2-foodItemDiscount">{discount}</span>
                        ) : null}
                      </div>
                      {qty > 0 ? (
                        <div className="wf2-foodQty">
                          <button
                            className="wf2-foodQtyBtn"
                            type="button"
                            onClick={() => removeItem(item.id)}
                            aria-label={`Remove ${item.name}`}
                          >
                            <Minus size={14} />
                          </button>
                          <span>{qty}</span>
                          <button
                            className="wf2-foodQtyBtn"
                            type="button"
                            onClick={() => addItem(item.id)}
                            aria-label={`Add ${item.name}`}
                          >
                            <Plus size={14} />
                          </button>
                        </div>
                      ) : (
                        <button
                          className="wf2-foodAddBtn"
                          type="button"
                          onClick={() => addItem(item.id)}
                        >
                          Add
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
            {filteredItems.length === 0 ? (
              <div className="wf2-foodEmpty">No items match your search.</div>
            ) : null}
          </div>
        </div>

        <aside className="wf2-foodSidebar">
          <div className="wf2-foodSideCard">
            <div className="wf2-foodSideHeader">
              <h4 className="wf2-foodSideTitle">Ticket Price</h4>
              <span className="wf2-foodChip">1 Ticket</span>
            </div>
            <div className="wf2-foodSideRow">
              <span>Base Fare</span>
              <span>{formatPrice(TICKET_PRICE)}</span>
            </div>
            <div className="wf2-foodSideRow">
              <span>Convenience Fee</span>
              <span>{formatPrice(0)}</span>
            </div>
            <div className="wf2-foodSideTotal">
              <span>Total</span>
              <span>{formatPrice(ticketTotal)}</span>
            </div>
          </div>

          <div className="wf2-foodSideCard">
            <div className="wf2-foodSideHeader">
              <h4 className="wf2-foodSideTitle">Your Cart</h4>
              <span className="wf2-foodChip">{cartCount} Items</span>
            </div>

            {cartItems.length ? (
              cartItems.map((item) => (
                <div className="wf2-foodCartItem" key={item.id}>
                  <div>
                    <div className="wf2-foodCartName">{item.name}</div>
                    <div className="wf2-foodCartMeta">
                      {formatPrice(item.price)} x {cart[item.id]}
                    </div>
                  </div>
                  <div className="wf2-foodQty">
                    <button
                      className="wf2-foodQtyBtn"
                      type="button"
                      onClick={() => removeItem(item.id)}
                      aria-label={`Remove ${item.name}`}
                    >
                      <Minus size={14} />
                    </button>
                    <span>{cart[item.id]}</span>
                    <button
                      className="wf2-foodQtyBtn"
                      type="button"
                      onClick={() => addItem(item.id)}
                      aria-label={`Add ${item.name}`}
                    >
                      <Plus size={14} />
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <div className="wf2-foodEmpty">Your cart is empty.</div>
            )}

            <div className="wf2-foodSideDivider" />
            <div className="wf2-foodSideRow">
              <span>Food Subtotal</span>
              <span>{formatPrice(cartTotal)}</span>
            </div>
            <div className="wf2-foodSideTotal">
              <span>Grand Total</span>
              <span>{formatPrice(orderTotal)}</span>
            </div>
            <button
              className="wf2-foodCheckout"
              type="button"
              onClick={() => goToOrderConfirm(buildOrderItems())}
            >
              Checkout
            </button>
            <button
              className="wf2-foodSkipText"
              type="button"
              onClick={() => goToOrderConfirm([])}
            >
              Skip food and beverages
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}
