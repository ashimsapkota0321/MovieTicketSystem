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

export async function fetchMovies() {
  const data = await request("/api/movies/");
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
  const data = await request("/api/admin/movies/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data;
}

export async function updateMovie(movieId, payload) {
  const data = await request(`/api/admin/movies/${movieId}/`, {
    method: "PUT",
    body: JSON.stringify(payload),
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
  return data?.show;
}

export async function deleteShow(showId) {
  await request(`/api/shows/${showId}/`, { method: "DELETE" });
  return true;
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

export async function fetchCinemas() {
  const data = await request("/api/cinemas/");
  return data?.vendors || [];
}

export async function fetchVendorsAdmin() {
  const data = await request("/api/admin/vendors/");
  return data?.vendors || [];
}

export async function fetchUsersAdmin() {
  const data = await request("/api/admin/users/");
  return data?.users || [];
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
