import React, { useMemo, useState } from "react";
import { ChevronLeft, Search, Plus, Minus } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import "../css/foodBeverage.css";
import gharjwai from "../images/gharjwai.jpg";
import foodItemImage from "../images/food-item.png";

const CATEGORIES = ["All", "Popcorn", "Beverages", "Combos", "Snacks", "Desserts"];

const FOOD_ITEMS = [
  {
    id: "popcorn-salt",
    name: "Regular Salt Pop Corn 80g",
    desc: "Allergen: Milk | Popcorn 80g | 425 kcal",
    price: 250,
    originalPrice: 300,
    category: "Popcorn",
    tag: "Bestseller",
    color: "linear-gradient(135deg, #f59e0b, #f6d35e)",
    image: foodItemImage,
    isVeg: true,
  },
  {
    id: "popcorn-cheese",
    name: "Cheese Pop Corn 80g",
    desc: "Allergen: Milk | Popcorn 80g | 435 kcal",
    price: 320,
    category: "Popcorn",
    color: "linear-gradient(135deg, #f97316, #fb7185)",
    image: foodItemImage,
    isVeg: true,
  },
  {
    id: "popcorn-caramel",
    name: "Caramel Pop Corn 90g",
    desc: "Allergen: Milk | Popcorn 90g | 445 kcal",
    price: 340,
    originalPrice: 400,
    category: "Popcorn",
    color: "linear-gradient(135deg, #f59e0b, #fbbf24)",
    image: foodItemImage,
    isVeg: true,
  },
  {
    id: "cola-regular",
    name: "Cola 500ml",
    desc: "Chilled | 0.5L | 210 kcal",
    price: 180,
    category: "Beverages",
    color: "linear-gradient(135deg, #38bdf8, #0ea5e9)",
    image: foodItemImage,
    isVeg: true,
  },
  {
    id: "lemonade",
    name: "Fresh Lemonade 350ml",
    desc: "Cold pressed | 350ml | 120 kcal",
    price: 220,
    category: "Beverages",
    color: "linear-gradient(135deg, #22c55e, #84cc16)",
    image: foodItemImage,
    isVeg: true,
  },
  {
    id: "combo-classic",
    name: "Classic Combo",
    desc: "Salt Pop Corn + Cola | 2 items",
    price: 520,
    category: "Combos",
    tag: "Value",
    color: "linear-gradient(135deg, #818cf8, #a78bfa)",
    image: foodItemImage,
    isVeg: true,
  },
  {
    id: "combo-family",
    name: "Family Combo",
    desc: "Large Pop Corn + 2 Cola | 3 items",
    price: 780,
    category: "Combos",
    color: "linear-gradient(135deg, #f472b6, #fb7185)",
    image: foodItemImage,
    isVeg: true,
  },
  {
    id: "nachos",
    name: "Classic Nachos",
    desc: "Cheese dip | 1 serving | 410 kcal",
    price: 350,
    category: "Snacks",
    color: "linear-gradient(135deg, #f97316, #f59e0b)",
    image: foodItemImage,
    isVeg: true,
  },
  {
    id: "hotdog",
    name: "Loaded Hot Dog",
    desc: "Sausage, sauce, cheese | 1 serving",
    price: 380,
    category: "Snacks",
    color: "linear-gradient(135deg, #ef4444, #fb7185)",
    image: foodItemImage,
    isVeg: false,
  },
  {
    id: "churros",
    name: "Cinnamon Churros",
    desc: "6 pcs | Chocolate dip | 320 kcal",
    price: 260,
    category: "Desserts",
    color: "linear-gradient(135deg, #c084fc, #f0abfc)",
    image: foodItemImage,
    isVeg: true,
  },
  {
    id: "brownie",
    name: "Fudge Brownie",
    desc: "Chocolate | 1 piece | 280 kcal",
    price: 240,
    category: "Desserts",
    color: "linear-gradient(135deg, #a78bfa, #818cf8)",
    image: foodItemImage,
    isVeg: true,
  },
  {
    id: "water",
    name: "Mineral Water 500ml",
    desc: "Chilled | 0.5L",
    price: 80,
    category: "Beverages",
    color: "linear-gradient(135deg, #22d3ee, #38bdf8)",
    image: foodItemImage,
    isVeg: true,
  },
];

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
  const [activeCategory, setActiveCategory] = useState("All");
  const [query, setQuery] = useState("");
  const [cart, setCart] = useState({});

  const filteredItems = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return FOOD_ITEMS.filter((item) => {
      const matchesCategory = activeCategory === "All" || item.category === activeCategory;
      const matchesQuery =
        !normalizedQuery ||
        item.name.toLowerCase().includes(normalizedQuery) ||
        item.desc.toLowerCase().includes(normalizedQuery);
      return matchesCategory && matchesQuery;
    });
  }, [activeCategory, query]);

  const cartItems = useMemo(
    () => FOOD_ITEMS.filter((item) => cart[item.id]),
    [cart]
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
            {CATEGORIES.map((category) => (
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
