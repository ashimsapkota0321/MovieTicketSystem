import { getAuthHeaders } from "./authSession";

const API_BASE =
  import.meta.env.VITE_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...getAuthHeaders(),
      ...(options.headers || {}),
    },
    ...options,
  });

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message = data?.message || data?.error || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data;
}

async function requestForm(path, formData, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      Accept: "application/json",
      ...getAuthHeaders(),
      ...(options.headers || {}),
    },
    body: formData,
    ...options,
  });

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const message = data?.message || data?.error || `Request failed (${response.status})`;
    throw new Error(message);
  }
  return data;
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

export async function createTestBookingSuccess(payload = {}) {
  const normalizedPayload =
    payload && typeof payload === "object" && !Array.isArray(payload)
      ? payload
      : {};
  const requestPayload =
    normalizedPayload.order && typeof normalizedPayload.order === "object"
      ? normalizedPayload
      : { order: normalizedPayload };
  const data = await request("/api/payment/qr/", {
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

export async function calculateBookingTicketPrice(payload) {
  const data = await request("/api/booking/ticket-price/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
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
  const data = await request("/api/vendor/food-items/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.item || data;
}

export async function updateVendorFoodItem(itemId, payload) {
  const data = await request(`/api/vendor/food-items/${itemId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
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

export async function validateVendorTicket(reference) {
  const data = await request("/api/vendor/ticket-validation/scan/", {
    method: "POST",
    body: JSON.stringify({ reference }),
  });
  return data || {};
}

export async function fetchVendorTicketValidationMonitor(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(
    `/api/vendor/ticket-validation/monitor/${query ? `?${query}` : ""}`
  );
  return data || {};
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
  const response = await fetch(`${API_BASE}/api/vendor/bulk-ticket-batches/${batchId}/export/`, {
    headers: {
      ...getAuthHeaders(),
      Accept: "text/csv",
    },
    method: "GET",
  });

  if (!response.ok) {
    let message = `Export failed (${response.status})`;
    try {
      const payload = await response.json();
      message = payload?.message || payload?.error || message;
    } catch {
      // no-op
    }
    throw new Error(message);
  }

  const disposition = response.headers.get("Content-Disposition") || "";
  const filenameMatch = disposition.match(/filename="?([^\"]+)"?/i);
  const filename = filenameMatch?.[1] || `bulk_tickets_batch_${batchId}.csv`;
  const blob = await response.blob();
  return { blob, filename };
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
