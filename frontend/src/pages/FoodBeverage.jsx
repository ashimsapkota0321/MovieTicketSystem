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
  const totalQuantity = cartItems.reduce((sum, item) => sum + (cart[item.id] || 0), 0);
  const selectedSeats = Array.isArray(state.selectedSeats) ? state.selectedSeats : [];
  const ticketCount = selectedSeats.length > 0 ? selectedSeats.length : 1;
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
          image: item.imageUrl || item.itemImage || item.image || "",
          isVeg:
            typeof item.isVeg === "boolean"
              ? item.isVeg
              : typeof item.is_veg === "boolean"
                ? item.is_veg
                : true,
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

  const formatCurrency = (value) => {
    const amount = Number(value || 0);
    return `Npr ${amount.toLocaleString("en-NP", {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    })}`;
  };
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
      <div className="wf2-foodHeroTop">
        <button
          className="wf2-foodBackBtn"
          type="button"
          onClick={() => navigate(-1)}
          aria-label="Go back"
        >
          <ChevronLeft size={18} />
        </button>
        <h2>Grab a Bite!</h2>
      </div>

      <div className="wf2-foodLayout wf2-foodLayoutImage">
        <div className="wf2-foodPanelWrap">
          <section className="wf2-foodHeaderPanel wf2-foodHeaderPanelFlat">
            <div className="wf2-foodToolbar wf2-foodToolbarImage">
              <div className="wf2-foodTabs wf2-foodTabsImage">
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

              <div className="wf2-foodSearch wf2-foodSearchImage">
                <Search size={18} />
                <input
                  type="text"
                  placeholder="Search for food items"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  aria-label="Search food items"
                />
              </div>
            </div>
          </section>

          <div className="wf2-foodGrid wf2-foodGridImage">
            {loadingItems ? <div className="wf2-foodEmpty">Loading food items...</div> : null}
            {filteredItems.map((item) => {
              const qty = cart[item.id] || 0;
              const discount = discountLabel(item);
              const thumbStyle = item.image
                ? { background: "#ffffff" }
                : { background: item.color };

              return (
                <article className="wf2-foodItemCard wf2-foodItemCardImage" key={item.id}>
                  <div className="wf2-foodVegFlag" aria-hidden="true">
                    <span className={item.isVeg ? "veg" : "nonveg"} />
                  </div>

                  <div className="wf2-foodThumb wf2-foodThumbImage" style={thumbStyle}>
                    {item.image ? <img src={item.image} alt={item.name} loading="lazy" /> : null}
                  </div>

                  <div className="wf2-foodItemBody wf2-foodItemBodyImage">
                    <h4 className="wf2-foodItemName">{item.name}</h4>
                    <p className="wf2-foodItemDesc">{item.tag || item.desc}</p>

                    <div className="wf2-foodItemFooter wf2-foodItemFooterImage">
                      <div className="wf2-foodItemPriceRow">
                        <span className="wf2-foodItemPrice">{formatCurrency(item.price)}</span>
                        {item.originalPrice ? (
                          <span className="wf2-foodItemPriceOld">
                            {formatCurrency(item.originalPrice)}
                          </span>
                        ) : null}
                        {discount ? <span className="wf2-foodItemDiscount">{discount}</span> : null}
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
                          className="wf2-foodAddBtn wf2-foodAddBtnImage"
                          type="button"
                          onClick={() => addItem(item.id)}
                        >
                          Add
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}

            {!loadingItems && filteredItems.length === 0 ? (
              <div className="wf2-foodEmpty">No items match your search.</div>
            ) : null}
          </div>
        </div>

        <aside className="wf2-foodSidebar wf2-foodSidebarImage">
          <div className="wf2-foodSideCard wf2-foodSummaryCard">
            <div className="wf2-foodSummaryHead">
              <strong>Ticket Price</strong>
              <span>{ticketCount} Ticket{ticketCount > 1 ? "s" : ""}</span>
            </div>
            <div className="wf2-foodSummaryRow">
              <span>Base Fare</span>
              <strong>{formatCurrency(ticketTotal)}</strong>
            </div>
            <div className="wf2-foodSummaryRow">
              <span>Convenience Fee</span>
              <strong>{formatCurrency(0)}</strong>
            </div>
            <div className="wf2-foodSummaryRow wf2-foodSummaryTotal">
              <span>Total</span>
              <strong>{formatCurrency(ticketTotal)}</strong>
            </div>
          </div>

          <div className="wf2-foodSideCard wf2-foodCartCardImage">
            <div className="wf2-foodSummaryHead">
              <strong>Your Cart</strong>
              <span>{totalQuantity} Item{totalQuantity > 1 ? "s" : ""}</span>
            </div>

            <div className="wf2-foodOrderList wf2-foodOrderListImage">
              {cartItems.length ? (
                cartItems.map((item) => (
                  <div className="wf2-foodOrderRow wf2-foodOrderRowImage" key={item.id}>
                    <div>
                      <div className="wf2-foodOrderName">{item.name}</div>
                      <div className="wf2-foodOrderMeta">{formatCurrency(item.price)} x {cart[item.id]}</div>
                    </div>

                    <div className="wf2-foodCartQtyInline">
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
                <div className="wf2-foodOrderEmpty">No Items Selected</div>
              )}
            </div>

            <div className="wf2-foodSummaryRow">
              <span>Food Subtotal</span>
              <strong>{formatCurrency(cartTotal)}</strong>
            </div>
            <div className="wf2-foodSummaryRow wf2-foodSummaryTotal">
              <span>Grand Total</span>
              <strong>{formatCurrency(orderTotal)}</strong>
            </div>

            <button
              className="wf2-foodProceedBtn wf2-foodProceedBtnImage"
              type="button"
              onClick={() => goToOrderConfirm(buildOrderItems())}
              disabled={!cartCount}
            >
              Checkout
            </button>

            <button
              className="wf2-foodSkipBtnInline"
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
