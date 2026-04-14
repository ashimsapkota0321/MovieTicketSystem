import { getAuthHeaders } from "./authSession";
import { logError, logInfo } from "./clientLogger";
import { API_BASE } from "./apiBase";
const MONITOR_EXPORT_POLL_INTERVAL_MS = 1200;
const MONITOR_EXPORT_TIMEOUT_MS = 60000;
const REQUEST_ID_HEADER = "X-Request-ID";

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function createRequestId() {
  if (typeof globalThis !== "undefined" && globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }
  return `req-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function normalizeMethod(value) {
  return String(value || "GET").trim().toUpperCase();
}

function buildRequestError({ message, response, payload, requestId, method, path, durationMs }) {
  const error = new Error(message);
  error.requestId = requestId;
  error.status = response.status;
  error.payload = payload;
  logError("API request failed", {
    requestId,
    method,
    path,
    status: response.status,
    durationMs,
    message,
  });
  return error;
}

function buildNetworkRequestError({ error, requestId, method, path, durationMs }) {
  const wrapped = new Error(
    `Unable to reach API server at ${API_BASE}. Please ensure backend is running on port 8000.`
  );
  wrapped.requestId = requestId;
  wrapped.method = method;
  wrapped.path = path;
  wrapped.cause = error;
  logError("API network request failed", {
    requestId,
    method,
    path,
    durationMs,
    message: error?.message || "Network request failed",
  });
  return wrapped;
}

async function request(path, options = {}) {
  const {
    requestId: explicitRequestId,
    headers: optionHeaders = {},
    ...fetchOptions
  } = options;
  const method = normalizeMethod(fetchOptions.method);
  const requestId = explicitRequestId || createRequestId();
  const startedAt = Date.now();

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...getAuthHeaders(),
        [REQUEST_ID_HEADER]: requestId,
        ...optionHeaders,
      },
      ...fetchOptions,
    });
  } catch (error) {
    const durationMs = Date.now() - startedAt;
    throw buildNetworkRequestError({
      error,
      requestId,
      method,
      path,
      durationMs,
    });
  }
  const resolvedRequestId = response.headers.get(REQUEST_ID_HEADER) || requestId;
  const durationMs = Date.now() - startedAt;

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message = data?.message || data?.error || `Request failed (${response.status})`;
    throw buildRequestError({
      message,
      response,
      payload: data,
      requestId: resolvedRequestId,
      method,
      path,
      durationMs,
    });
  }

  logInfo("API request completed", {
    requestId: resolvedRequestId,
    method,
    path,
    status: response.status,
    durationMs,
  });

  return data;
}

async function requestForm(path, formData, options = {}) {
  const {
    requestId: explicitRequestId,
    headers: optionHeaders = {},
    ...fetchOptions
  } = options;
  const method = normalizeMethod(fetchOptions.method);
  const requestId = explicitRequestId || createRequestId();
  const startedAt = Date.now();

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: {
        Accept: "application/json",
        ...getAuthHeaders(),
        [REQUEST_ID_HEADER]: requestId,
        ...optionHeaders,
      },
      body: formData,
      ...fetchOptions,
    });
  } catch (error) {
    const durationMs = Date.now() - startedAt;
    throw buildNetworkRequestError({
      error,
      requestId,
      method,
      path,
      durationMs,
    });
  }
  const resolvedRequestId = response.headers.get(REQUEST_ID_HEADER) || requestId;
  const durationMs = Date.now() - startedAt;

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message = data?.message || data?.error || `Request failed (${response.status})`;
    throw buildRequestError({
      message,
      response,
      payload: data,
      requestId: resolvedRequestId,
      method,
      path,
      durationMs,
    });
  }

  logInfo("API form request completed", {
    requestId: resolvedRequestId,
    method,
    path,
    status: response.status,
    durationMs,
  });

  return data;
}

async function requestBlob(path, options = {}) {
  const {
    requestId: explicitRequestId,
    headers: optionHeaders = {},
    ...fetchOptions
  } = options;
  const method = normalizeMethod(fetchOptions.method);
  const requestId = explicitRequestId || createRequestId();
  const startedAt = Date.now();

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: {
        Accept: "application/octet-stream",
        ...getAuthHeaders(),
        [REQUEST_ID_HEADER]: requestId,
        ...optionHeaders,
      },
      ...fetchOptions,
    });
  } catch (error) {
    const durationMs = Date.now() - startedAt;
    throw buildNetworkRequestError({
      error,
      requestId,
      method,
      path,
      durationMs,
    });
  }
  const resolvedRequestId = response.headers.get(REQUEST_ID_HEADER) || requestId;
  const durationMs = Date.now() - startedAt;

  if (!response.ok) {
    let payload = null;
    let message = `Request failed (${response.status})`;
    try {
      payload = await response.json();
      message = payload?.message || payload?.error || message;
    } catch {
      payload = null;
    }
    throw buildRequestError({
      message,
      response,
      payload,
      requestId: resolvedRequestId,
      method,
      path,
      durationMs,
    });
  }

  logInfo("API file request completed", {
    requestId: resolvedRequestId,
    method,
    path,
    status: response.status,
    durationMs,
  });

  return {
    response,
    requestId: resolvedRequestId,
  };
}

export async function fetchMovies(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/movies/${query ? `?${query}` : ""}`);
  return data?.movies || [];
}

export async function fetchMovieById(movieId) {
  const data = await request(`/api/movies/${movieId}/`);
  return data?.movie;
}

export async function fetchMovieBySlug(slug) {
  const data = await request(`/api/movies/slug/${encodeURIComponent(slug)}/`);
  return data?.movie;
}

export async function createMovie(payload) {
  if (payload instanceof FormData) {
    const data = await requestForm("/api/admin/movies/", payload, { method: "POST" });
    return data?.movie || data;
  }
  const data = await request("/api/admin/movies/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data;
}

export async function updateMovie(movieId, payload) {
  if (payload instanceof FormData) {
    const data = await requestForm(`/api/admin/movies/${movieId}/`, payload, {
      method: "PATCH",
    });
    return data?.movie || data;
  }
  const data = await request(`/api/admin/movies/${movieId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return data;
}

export async function createVendorMovie(formData) {
  const data = await requestForm("/api/movies/", formData, { method: "POST" });
  return data?.movie || data;
}

export async function updateMovieTrailer(movieId, trailerUrl) {
  const data = await request(`/api/admin/movies/${movieId}/`, {
    method: "PATCH",
    body: JSON.stringify({
      trailer_url: trailerUrl || "",
    }),
  });
  return data;
}

export async function deleteMovie(movieId) {
  await request(`/api/admin/movies/${movieId}/`, { method: "DELETE" });
  return true;
}

export async function fetchShows(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/shows/${query ? `?${query}` : ""}`);
  return data?.shows || [];
}

export async function fetchTrailers() {
  const data = await request("/api/trailers/");
  return data?.trailers || [];
}

export async function fetchBanners(page) {
  const query = page ? `?page=${encodeURIComponent(page)}` : "";
  const data = await request(`/api/banners/active/${query}`);
  return data?.banners || [];
}

export async function createMovieReview(movieId, payload) {
  const data = await request(`/api/movies/${movieId}/reviews/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.movie;
}

export async function updateMovieReview(reviewId, payload) {
  const data = await request(`/api/reviews/${reviewId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return data?.review || data;
}

export async function deleteMovieReview(reviewId) {
  await request(`/api/reviews/${reviewId}/`, {
    method: "DELETE",
  });
  return true;
}

export async function fetchPersonDetail(slug) {
  const data = await request(`/api/person/${encodeURIComponent(slug)}/`);
  return data?.person;
}

export async function fetchPeople(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/people/${query ? `?${query}` : ""}`);
  if (Array.isArray(data)) return data;
  return data?.results || [];
}

export async function createPerson(payload) {
  const data = await request("/api/people/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data;
}

export async function updatePerson(personId, payload) {
  const data = await request(`/api/people/${personId}/`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return data;
}

export async function deletePerson(personId) {
  await request(`/api/people/${personId}/`, { method: "DELETE" });
  return true;
}

export async function fetchAdminBanners() {
  const data = await request("/api/admin/banners/");
  return data?.banners || [];
}

export async function createBanner(formData) {
  const data = await requestForm("/api/admin/banners/", formData, { method: "POST" });
  return data?.banner;
}

export async function updateBanner(bannerId, formData, options = {}) {
  const data = await requestForm(`/api/admin/banners/${bannerId}/`, formData, {
    method: options.method || "PUT",
  });
  return data?.banner;
}

export async function deleteBanner(bannerId) {
  await request(`/api/admin/banners/${bannerId}/`, { method: "DELETE" });
  return true;
}


export async function createShow(payload) {
  const data = await request("/api/shows/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data || {};
}

export async function initiateEsewaPayment(payloadOrAmount) {
  const payload =
    payloadOrAmount && typeof payloadOrAmount === "object"
      ? payloadOrAmount
      : { amount: payloadOrAmount };
  const data = await request("/api/payment/esewa/initiate/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data || {};
}

export async function verifyEsewaPayment(payloadOrData) {
  const payload =
    payloadOrData && typeof payloadOrData === "object"
      ? payloadOrData
      : { data: payloadOrData };
  const data = await request("/api/payment/esewa/verify/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data || {};
}

export async function initiateUserWalletTopupEsewa(payloadOrAmount) {
  const payload =
    payloadOrAmount && typeof payloadOrAmount === "object"
      ? payloadOrAmount
      : { amount: payloadOrAmount };
  const data = await request("/api/user/wallet/topup/esewa/initiate/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function verifyUserWalletTopupEsewa(payloadOrData) {
  const payload =
    payloadOrData && typeof payloadOrData === "object"
      ? payloadOrData
      : { data: payloadOrData };
  const data = await request("/api/user/wallet/topup/esewa/verify/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function payBookingWithUserWallet(payload = {}) {
  const normalizedPayload =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? payload
      : {};
  const requestPayload =
    normalizedPayload.order && typeof normalizedPayload.order === "object"
      ? normalizedPayload
      : { order: normalizedPayload };
  const data = await request("/api/user/wallet/booking/pay/", {
    method: "POST",
    body: JSON.stringify(requestPayload),
  });
  return data || {};
}

export async function deleteShow(showId) {
  await request(`/api/shows/${showId}/`, { method: "DELETE" });
  return true;
}

export async function fetchVendorQuickHallSwapPreview(showId) {
  const data = await request(`/api/vendor/shows/${showId}/quick-hall-swap/`);
  return data || {};
}

export async function runVendorQuickHallSwap(showId, payload) {
  const data = await request(`/api/vendor/shows/${showId}/quick-hall-swap/`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchBookingSeatLayout(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/booking/seat-layout/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function fetchVendorSeatLayout(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/vendor/seat-layout/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function fetchVendorHalls(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/vendor/halls/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function createVendorHall(payload = {}) {
  const data = await request("/api/vendor/halls/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function saveVendorSeatLayout(payload) {
  const data = await request("/api/vendor/seat-layout/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data || {};
}

export async function updateVendorSeatStatus(payload) {
  const data = await request("/api/vendor/seat-status/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data || {};
}

export async function fetchVendorPricingRules(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/vendor/pricing-rules/${query ? `?${query}` : ""}`);
  return data?.rules || [];
}

export async function createVendorPricingRule(payload) {
  const data = await request("/api/vendor/pricing-rules/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.rule || data;
}

export async function updateVendorPricingRule(ruleId, payload) {
  const data = await request(`/api/vendor/pricing-rules/${ruleId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return data?.rule || data;
}

export async function deleteVendorPricingRule(ruleId) {
  const data = await request(`/api/vendor/pricing-rules/${ruleId}/`, {
    method: "DELETE",
  });
  return data;
}

export async function fetchVendorShowBasePrices(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/vendor/show-base-prices/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function saveVendorShowBasePrices(payload) {
  const data = await request("/api/vendor/show-base-prices/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchAdminPricingRules(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/admin/pricing-rules/${query ? `?${query}` : ""}`);
  return data?.rules || [];
}

export async function createAdminPricingRule(payload) {
  const data = await request("/api/admin/pricing-rules/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data?.rule || data;
}

export async function updateAdminPricingRule(ruleId, payload) {
  const data = await request(`/api/admin/pricing-rules/${ruleId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload || {}),
  });
  return data?.rule || data;
}

export async function deleteAdminPricingRule(ruleId) {
  const data = await request(`/api/admin/pricing-rules/${ruleId}/`, {
    method: "DELETE",
  });
  return data || {};
}

export async function fetchVendorLoyaltyRule() {
  const data = await request("/api/vendor/loyalty/rules/");
  return data?.rule || data;
}

export async function updateVendorLoyaltyRule(payload) {
  const data = await request("/api/vendor/loyalty/rules/", {
    method: "PATCH",
    body: JSON.stringify(payload || {}),
  });
  return data?.rule || data;
}

export async function fetchVendorLoyaltyRewards() {
  const data = await request("/api/vendor/loyalty/rewards/");
  return data?.rewards || [];
}

export async function createVendorLoyaltyReward(payload) {
  const data = await request("/api/vendor/loyalty/rewards/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function updateVendorLoyaltyReward(rewardId, payload) {
  const data = await request(`/api/vendor/loyalty/rewards/${rewardId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function deleteVendorLoyaltyReward(rewardId) {
  const data = await request(`/api/vendor/loyalty/rewards/${rewardId}/`, {
    method: "DELETE",
  });
  return data || {};
}

export async function fetchVendorLoyaltyPromotions() {
  const data = await request("/api/vendor/loyalty/promotions/");
  return data?.promotions || [];
}

export async function createVendorLoyaltyPromotion(payload) {
  const data = await request("/api/vendor/loyalty/promotions/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function updateVendorLoyaltyPromotion(promotionId, payload) {
  const data = await request(`/api/vendor/loyalty/promotions/${promotionId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function deleteVendorLoyaltyPromotion(promotionId) {
  const data = await request(`/api/vendor/loyalty/promotions/${promotionId}/`, {
    method: "DELETE",
  });
  return data || {};
}

export async function fetchAdminLoyaltyControls() {
  const data = await request("/api/admin/loyalty/rules/");
  return data || {};
}

export async function updateAdminLoyaltyRule(payload) {
  const data = await request("/api/admin/loyalty/rules/", {
    method: "PATCH",
    body: JSON.stringify(payload || {}),
  });
  return data?.rule || data;
}

export async function fetchAdminLoyaltyRewards() {
  const data = await request("/api/admin/loyalty/rewards/");
  return data?.rewards || [];
}

export async function createAdminLoyaltyReward(payload) {
  const data = await request("/api/admin/loyalty/rewards/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data?.reward || data;
}

export async function updateAdminLoyaltyReward(rewardId, payload) {
  const data = await request(`/api/admin/loyalty/rewards/${rewardId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload || {}),
  });
  return data?.reward || data;
}

export async function deleteAdminLoyaltyReward(rewardId) {
  const data = await request(`/api/admin/loyalty/rewards/${rewardId}/`, {
    method: "DELETE",
  });
  return data || {};
}

export async function fetchAdminLoyaltyPromotions() {
  const data = await request("/api/admin/loyalty/promotions/");
  return data?.promotions || [];
}

export async function createAdminLoyaltyPromotion(payload) {
  const data = await request("/api/admin/loyalty/promotions/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data?.promotion || data;
}

export async function updateAdminLoyaltyPromotion(promotionId, payload) {
  const data = await request(`/api/admin/loyalty/promotions/${promotionId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload || {}),
  });
  return data?.promotion || data;
}

export async function deleteAdminLoyaltyPromotion(promotionId) {
  const data = await request(`/api/admin/loyalty/promotions/${promotionId}/`, {
    method: "DELETE",
  });
  return data || {};
}

export async function fetchVendorOffers(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/vendor/offers/${query ? `?${query}` : ""}`);
  return data?.offers || [];
}

export async function createVendorOffer(payload) {
  const data = await request("/api/vendor/offers/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data?.offer || data;
}

export async function updateVendorOffer(offerId, payload) {
  const data = await request(`/api/vendor/offers/${offerId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload || {}),
  });
  return data?.offer || data;
}

export async function deleteVendorOffer(offerId) {
  const data = await request(`/api/vendor/offers/${offerId}/`, {
    method: "DELETE",
  });
  return data || {};
}

export async function calculateBookingTicketPrice(payload) {
  const data = await request("/api/booking/ticket-price/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data || {};
}

export async function previewBookingTicketPrice(payload) {
  const data = await request("/api/booking/price-preview/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchBookingDynamicPrice(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/booking/dynamic-price/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function applyBookingCoupon(payload) {
  const data = await request("/api/booking/coupon/apply/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data || {};
}

export async function reserveBookingSeats(payload) {
  const data = await request("/api/booking/seat-reserve/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data || {};
}

export async function releaseBookingSeats(payload) {
  const data = await request("/api/booking/seat-release/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data || {};
}

export async function createBookingResumeNotification(payload) {
  const data = await request("/api/booking/resume-notification/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchCustomerBookingHistory() {
  const data = await request("/api/bookings/history/");
  return data?.bookings || [];
}

export async function fetchCustomerBookingHistoryDetail(bookingId) {
  const data = await request(`/api/bookings/history/${bookingId}/`);
  return data?.booking || data;
}

export async function cancelCustomerBookingHistory(bookingId, payload = {}) {
  const data = await request(`/api/bookings/history/${bookingId}/cancel/`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchLoyaltyDashboard() {
  const data = await request("/api/loyalty/dashboard/");
  return data || {};
}

export async function fetchLoyaltyTransactions(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/loyalty/transactions/${query ? `?${query}` : ""}`);
  return data?.transactions || [];
}

export async function fetchLoyaltyRewards(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/loyalty/rewards/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function previewLoyaltyCheckout(payload) {
  const data = await request("/api/loyalty/checkout/preview/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data?.preview || data;
}

export async function redeemLoyaltyReward(payload) {
  const data = await request("/api/loyalty/rewards/redeem/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchLoyaltyRedemptions(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/loyalty/redemptions/${query ? `?${query}` : ""}`);
  return data?.redemptions || [];
}

export async function applyReferralLoyaltyBonus(payload) {
  const data = await request("/api/loyalty/referral/bonus/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchSubscriptionPlans(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/subscriptions/plans/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function fetchSubscriptionPlanDetail(planId, params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/subscriptions/plans/${planId}/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function fetchSubscriptionDashboard(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/subscriptions/dashboard/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function fetchActiveSubscription(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/subscriptions/active/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function previewSubscriptionCheckout(payload) {
  const data = await request("/api/subscriptions/checkout/preview/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data?.preview || data;
}

export async function subscribeToPlan(payload) {
  const data = await request("/api/subscriptions/subscribe/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function upgradeSubscription(payload) {
  const data = await request("/api/subscriptions/upgrade/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function cancelSubscription(payload = {}) {
  const data = await request("/api/subscriptions/cancel/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function renewSubscription(payload = {}) {
  const data = await request("/api/subscriptions/renew/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function pauseSubscription(payload = {}) {
  const data = await request("/api/subscriptions/pause/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function resumeSubscription(payload = {}) {
  const data = await request("/api/subscriptions/resume/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchVendorSubscriptionPlans() {
  const data = await request("/api/vendor/subscriptions/plans/");
  return data?.plans || [];
}

export async function createVendorSubscriptionPlan(payload) {
  const data = await request("/api/vendor/subscriptions/plans/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data?.plan || data;
}

export async function updateVendorSubscriptionPlan(planId, payload) {
  const data = await request(`/api/vendor/subscriptions/plans/${planId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload || {}),
  });
  return data?.plan || data;
}

export async function deleteVendorSubscriptionPlan(planId) {
  const data = await request(`/api/vendor/subscriptions/plans/${planId}/`, {
    method: "DELETE",
  });
  return data || {};
}

export async function fetchAdminSubscriptionPlans(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/admin/subscriptions/plans/${query ? `?${query}` : ""}`);
  return data?.plans || [];
}

export async function createAdminSubscriptionPlan(payload) {
  const data = await request("/api/admin/subscriptions/plans/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data?.plan || data;
}

export async function updateAdminSubscriptionPlan(planId, payload) {
  const data = await request(`/api/admin/subscriptions/plans/${planId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload || {}),
  });
  return data?.plan || data;
}

export async function deleteAdminSubscriptionPlan(planId, payload = {}) {
  const data = await request(`/api/admin/subscriptions/plans/${planId}/`, {
    method: "DELETE",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchReferralDashboard() {
  const data = await request("/api/referral/dashboard/");
  return data || {};
}

export async function fetchReferralWalletTransactions(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/referral/wallet/transactions/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function previewReferralWalletCheckout(payload) {
  const data = await request("/api/referral/wallet/preview/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data?.preview || data;
}

export async function fetchAdminReferralControls(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/admin/referrals/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function updateAdminReferralPolicy(payload) {
  const data = await request("/api/admin/referrals/", {
    method: "PATCH",
    body: JSON.stringify(payload || {}),
  });
  return data?.policy || data;
}

export async function updateAdminReferralStatus(referralId, payload) {
  const data = await request(`/api/admin/referrals/${referralId}/status/`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data?.referral || data;
}

export async function fetchUserWallet() {
  const data = await request("/api/user/wallet/");
  return data || {};
}

export async function fetchUserSubscription() {
  const data = await request("/api/user/subscription/");
  return data || {};
}

export async function redeemUserReward(payload) {
  const data = await request("/api/user/redeem/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchUserVendorOffers(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/user/offers/${query ? `?${query}` : ""}`);
  return data?.offers || [];
}

export async function fetchGroupBookingSessions(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/group-booking/sessions/${query ? `?${query}` : ""}`);
  return data?.sessions || [];
}

export async function createGroupBookingSession(payload) {
  const data = await request("/api/group-booking/sessions/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchGroupBookingSession(sessionId) {
  const data = await request(`/api/group-booking/sessions/${sessionId}/`);
  return data?.session || data;
}

export async function fetchGroupBookingSessionByInvite(inviteCode) {
  const data = await request(`/api/group-booking/invite/${encodeURIComponent(inviteCode)}/`);
  return data?.session || data;
}

export async function joinGroupBookingSession(inviteCode, payload = {}) {
  const data = await request(`/api/group-booking/invite/${encodeURIComponent(inviteCode)}/join/`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function assignGroupBookingSeats(sessionId, payload) {
  const data = await request(`/api/group-booking/sessions/${sessionId}/assign-seats/`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function applyGroupManualSplit(sessionId, payload) {
  const data = await request(`/api/group-booking/sessions/${sessionId}/manual-split/`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function initiateGroupBookingPayment(sessionId, payload = {}) {
  const data = await request(`/api/group-booking/sessions/${sessionId}/payments/initiate/`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function completeGroupBookingPayment(sessionId, paymentId, payload) {
  const data = await request(
    `/api/group-booking/sessions/${sessionId}/payments/${paymentId}/complete/`,
    {
      method: "POST",
      body: JSON.stringify(payload || {}),
    }
  );
  return data || {};
}

export async function dropOutGroupBookingSession(sessionId, payload = {}) {
  const data = await request(`/api/group-booking/sessions/${sessionId}/drop-out/`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function cancelGroupBookingSession(sessionId, payload = {}) {
  const data = await request(`/api/group-booking/sessions/${sessionId}/cancel/`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchNotifications(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/notifications/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function markNotificationsRead(payload = {}) {
  const data = await request("/api/notifications/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data || {};
}

export async function fetchCinemas(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/cinemas/${query ? `?${query}` : ""}`);
  return data?.vendors || [];
}

function buildFoodItemFormData(payload = {}) {
  const formData = new FormData();
  Object.entries(payload || {}).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    if (value instanceof File) {
      formData.append(key, value);
      return;
    }
    if (typeof value === "boolean") {
      formData.append(key, value ? "true" : "false");
      return;
    }
    formData.append(key, String(value));
  });
  return formData;
}

export async function fetchFoodItemsByVendor(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/food-items/${query ? `?${query}` : ""}`);
  return data?.items || [];
}

export async function fetchVendorFoodItems() {
  const data = await request("/api/vendor/food-items/");
  return data?.items || [];
}

export async function createVendorFoodItem(payload) {
  const data = await requestForm("/api/vendor/food-items/", buildFoodItemFormData(payload), {
    method: "POST",
  });
  return data?.item || data;
}

export async function updateVendorFoodItem(itemId, payload) {
  const data = await requestForm(
    `/api/vendor/food-items/${itemId}/`,
    buildFoodItemFormData(payload),
    {
    method: "PATCH",
    }
  );
  return data?.item || data;
}

export async function deleteVendorFoodItem(itemId) {
  await request(`/api/vendor/food-items/${itemId}/`, { method: "DELETE" });
  return true;
}

export async function fetchVendorsAdmin() {
  const data = await request("/api/admin/vendors/");
  return data?.vendors || [];
}

export async function fetchUsersAdmin() {
  const data = await request("/api/admin/users/");
  return data?.users || [];
}

export async function fetchAdminBookings() {
  const data = await request("/api/admin/bookings/");
  return data?.bookings || [];
}

export async function fetchAdminDropoffAnalytics() {
  const data = await request("/api/admin/analytics/dropoffs/");
  return data || {};
}

export async function fetchAdminCoupons() {
  const data = await request("/api/admin/coupons/");
  return data?.coupons || [];
}

export async function createAdminCoupon(payload) {
  const data = await request("/api/admin/coupons/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.coupon || data;
}

export async function updateAdminCoupon(couponId, payload) {
  const data = await request(`/api/admin/coupons/${couponId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return data?.coupon || data;
}

export async function deleteAdminCoupon(couponId) {
  const data = await request(`/api/admin/coupons/${couponId}/`, {
    method: "DELETE",
  });
  return data;
}

export async function fetchAdminBooking(bookingId) {
  const data = await request(`/api/admin/bookings/${bookingId}/`);
  return data?.booking;
}

export async function cancelAdminBooking(bookingId, payload = {}) {
  const data = await request(`/api/admin/bookings/${bookingId}/cancel/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.booking || data;
}

export async function refundAdminBooking(bookingId, payload = {}) {
  const data = await request(`/api/admin/bookings/${bookingId}/refund/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.booking || data;
}

export async function deleteAdminBooking(bookingId) {
  const data = await request(`/api/admin/bookings/${bookingId}/`, { method: "DELETE" });
  return data;
}

export async function createUserAdmin(payload) {
  const data = await request("/api/admin/users/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.user;
}

export async function updateUserAdmin(userId, payload, options = {}) {
  const data = await request(`/api/admin/users/${userId}/`, {
    method: options.method || "PUT",
    body: JSON.stringify(payload),
  });
  return data?.user;
}

export async function deleteUserAdmin(userId) {
  await request(`/api/admin/users/${userId}/`, { method: "DELETE" });
  return true;
}

export async function fetchVendorAnalytics() {
  const data = await request("/api/vendor/analytics/");
  return data;
}

export async function fetchVendorRevenueAnalytics(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/vendor/revenue/analytics/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function fetchVendorRevenueTransactions(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/vendor/revenue/transactions/${query ? `?${query}` : ""}`);
  return data?.transactions || [];
}

export async function fetchVendorRevenueReport(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/vendor/revenue/reports/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function fetchVendorWalletBalance() {
  const data = await request("/api/vendor/wallet/");
  return data || {};
}

export async function fetchVendorWalletTransactions(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/vendor/wallet/transactions/${query ? `?${query}` : ""}`);
  return data?.transactions || [];
}

export async function updateVendorPayoutProfile(payload = {}) {
  const data = await request("/api/vendor/wallet/payout-profile/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function requestVendorPayoutProfileVerification() {
  const data = await request("/api/vendor/wallet/payout-profile/request-verification/", {
    method: "POST",
    body: JSON.stringify({}),
  });
  return data || {};
}

export async function verifyVendorPayoutProfile(payload = {}) {
  const data = await request("/api/vendor/wallet/payout-profile/verify/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function requestVendorWithdrawal(payload = {}) {
  const data = await request("/api/vendor/wallet/withdraw/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function retryAdminWithdrawal(transactionId) {
  const data = await request(`/api/admin/withdrawals/${transactionId}/retry/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  return data || {};
}

export async function fetchAdminRevenueConfig() {
  const data = await request("/api/admin/revenue/config/");
  return data || {};
}

export async function updateAdminRevenueConfig(payload = {}) {
  const data = await request("/api/admin/revenue/config/", {
    method: "PATCH",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchAdminRevenueAnalytics(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/admin/revenue/analytics/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function fetchAdminRevenueTransactions(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/admin/revenue/transactions/${query ? `?${query}` : ""}`);
  return data?.transactions || [];
}

export async function fetchAdminRevenueReport(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/admin/revenue/reports/${query ? `?${query}` : ""}`);
  return data || {};
}

export async function fetchAdminWithdrawalRequests(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/admin/withdrawals/${query ? `?${query}` : ""}`);
  return data?.withdrawals || [];
}

export async function approveAdminWithdrawalRequest(transactionId, payload = {}) {
  const data = await request(`/api/admin/withdrawals/${transactionId}/approve/`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function rejectAdminWithdrawalRequest(transactionId, payload = {}) {
  const data = await request(`/api/admin/withdrawals/${transactionId}/reject/`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
  return data || {};
}

export async function fetchVendorBookings() {
  const data = await request("/api/vendor/bookings/");
  return data?.bookings || [];
}

export async function fetchVendorBooking(bookingId) {
  const data = await request(`/api/vendor/bookings/${bookingId}/`);
  return data?.booking;
}

export async function cancelVendorBooking(bookingId, payload = {}) {
  const data = await request(`/api/vendor/bookings/${bookingId}/cancel/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.booking || data;
}

export async function refundVendorBooking(bookingId, payload = {}) {
  const data = await request(`/api/vendor/bookings/${bookingId}/refund/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.booking || data;
}

export async function deleteVendorBooking(bookingId) {
  const data = await request(`/api/vendor/bookings/${bookingId}/delete/`, {
    method: "DELETE",
  });
  return data;
}

export async function validateVendorTicket(payloadOrReference) {
  const payload =
    payloadOrReference && typeof payloadOrReference === "object"
      ? payloadOrReference
      : { reference: payloadOrReference };
  try {
    const data = await request("/api/vendor/ticket-validation/scan/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return data || {};
  } catch (error) {
    const payloadData = error?.payload || null;
    const scanError = new Error(error?.message || "Request failed");
    scanError.code = String(payloadData?.code || "").trim().toUpperCase();
    scanError.alert = String(payloadData?.alert || "").trim().toLowerCase();
    scanError.retryAfterSeconds = Number(payloadData?.retryAfterSeconds || 0);
    scanError.status = Number(error?.status || 0);
    scanError.scan = payloadData?.scan || null;
    scanError.requestId = error?.requestId || "";
    throw scanError;
  }
}

export async function fetchVendorTicketValidationMonitor(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(
    `/api/vendor/ticket-validation/monitor/${query ? `?${query}` : ""}`
  );
  return data || {};
}

export async function createVendorTicketValidationMonitorExportJob(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(
    `/api/vendor/ticket-validation/monitor/export/jobs/${query ? `?${query}` : ""}`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
      },
    }
  );

  return data?.job || data || {};
}

export async function fetchVendorTicketValidationMonitorExportJob(jobId) {
  const data = await request(`/api/vendor/ticket-validation/monitor/export/jobs/${jobId}/`, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
  });

  return data?.job || data || {};
}

export async function downloadVendorTicketValidationMonitorExportJob(jobId) {
  const { response, requestId } = await requestBlob(
    `/api/vendor/ticket-validation/monitor/export/jobs/${jobId}/download/`,
    {
      method: "GET",
      headers: {
        Accept: "text/csv",
      },
    }
  );

  const disposition = response.headers.get("Content-Disposition") || "";
  const filenameMatch = disposition.match(/filename="?([^"]+)"?/i);
  const filename = filenameMatch?.[1] || "ticket_validation_monitor.csv";
  const blob = await response.blob();
  return { blob, filename, requestId };
}

async function waitForVendorTicketValidationMonitorExportJob(jobId, options = {}) {
  const timeoutMs = Math.max(Number(options.timeoutMs || MONITOR_EXPORT_TIMEOUT_MS), 1000);
  const pollIntervalMs = Math.max(
    Number(options.pollIntervalMs || MONITOR_EXPORT_POLL_INTERVAL_MS),
    300
  );
  const startedAt = Date.now();

  while (true) {
    const job = await fetchVendorTicketValidationMonitorExportJob(jobId);
    const statusValue = String(job?.status || "").trim().toUpperCase();
    if (statusValue === "COMPLETED") {
      return job;
    }
    if (statusValue === "FAILED") {
      throw new Error(job?.errorMessage || "Monitor CSV export failed.");
    }

    if (Date.now() - startedAt >= timeoutMs) {
      throw new Error("Monitor CSV export is taking longer than expected. Please try again shortly.");
    }

    await delay(pollIntervalMs);
  }
}

export async function exportVendorTicketValidationMonitorCsv(params = {}) {
  const queuedJob = await createVendorTicketValidationMonitorExportJob(params);
  const jobId = Number(queuedJob?.id || 0);
  if (!jobId) {
    throw new Error("Failed to queue monitor CSV export.");
  }

  const completedJob = await waitForVendorTicketValidationMonitorExportJob(jobId);
  const { blob, filename } = await downloadVendorTicketValidationMonitorExportJob(jobId);
  return {
    blob,
    filename: filename || completedJob?.filename || "ticket_validation_monitor.csv",
  };
}

export async function submitPrivateScreeningRequest(payload) {
  const data = await request("/api/private-screening-requests/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.request || data;
}

export async function fetchVendorPrivateScreeningRequests(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(
    `/api/vendor/private-screening-requests/${query ? `?${query}` : ""}`
  );
  return data?.requests || [];
}

export async function updateVendorPrivateScreeningRequest(requestId, payload) {
  const data = await request(`/api/vendor/private-screening-requests/${requestId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return data?.request || data;
}

export async function fetchVendorBulkTicketBatches(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/vendor/bulk-ticket-batches/${query ? `?${query}` : ""}`);
  return data?.batches || [];
}

export async function createVendorBulkTicketBatch(payload) {
  const data = await request("/api/vendor/bulk-ticket-batches/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.batch || data;
}

export async function exportVendorBulkTicketBatch(batchId) {
  const { response, requestId } = await requestBlob(
    `/api/vendor/bulk-ticket-batches/${batchId}/export/`,
    {
      method: "GET",
      headers: {
        Accept: "text/csv",
      },
    }
  );

  const disposition = response.headers.get("Content-Disposition") || "";
  const filenameMatch = disposition.match(/filename="?([^"]+)"?/i);
  const filename = filenameMatch?.[1] || `bulk_tickets_batch_${batchId}.csv`;
  const blob = await response.blob();
  return { blob, filename, requestId };
}

export async function fetchVendorStaffAccounts() {
  const data = await request("/api/vendor/staff/");
  return data?.staff || [];
}

export async function createVendorStaffAccount(payload) {
  const data = await request("/api/vendor/staff/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.staff || data;
}

export async function updateVendorStaffAccount(staffId, payload) {
  const data = await request(`/api/vendor/staff/${staffId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return data?.staff || data;
}

export async function fetchVendorPromoCodes(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/vendor/promo-codes/${query ? `?${query}` : ""}`);
  return data?.promo_codes || [];
}

export async function createVendorPromoCode(payload) {
  const data = await request("/api/vendor/promo-codes/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.promo_code || data;
}

export async function updateVendorPromoCode(promoId, payload) {
  const data = await request(`/api/vendor/promo-codes/${promoId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return data?.promo_code || data;
}

export async function deleteVendorPromoCode(promoId) {
  await request(`/api/vendor/promo-codes/${promoId}/`, { method: "DELETE" });
  return true;
}

export async function fetchVendorCampaigns(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/vendor/campaigns/${query ? `?${query}` : ""}`);
  return data?.campaigns || [];
}

export async function createVendorCampaign(payload) {
  const data = await request("/api/vendor/campaigns/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.campaign || data;
}

export async function updateVendorCampaign(campaignId, payload) {
  const data = await request(`/api/vendor/campaigns/${campaignId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return data?.campaign || data;
}

export async function runVendorCampaign(campaignId) {
  const data = await request(`/api/vendor/campaigns/${campaignId}/`, {
    method: "POST",
  });
  return data;
}
