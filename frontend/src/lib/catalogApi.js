const API_BASE =
  import.meta.env.VITE_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
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

export async function fetchMovies() {
  const data = await request("/api/movies/");
  return data?.movies || [];
}

export async function createMovie(payload) {
  const data = await request("/api/movies/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return data?.movie;
}

export async function updateMovie(movieId, payload) {
  const data = await request(`/api/movies/${movieId}/`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  return data?.movie;
}

export async function deleteMovie(movieId) {
  await request(`/api/movies/${movieId}/`, { method: "DELETE" });
  return true;
}

export async function fetchShows(params = {}) {
  const query = new URLSearchParams(params).toString();
  const data = await request(`/api/shows/${query ? `?${query}` : ""}`);
  return data?.shows || [];
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

export async function fetchCinemas() {
  const data = await request("/api/cinemas/");
  return data?.vendors || [];
}

export async function fetchVendorsAdmin() {
  const data = await request("/api/admin/vendors/");
  return data?.vendors || [];
}
