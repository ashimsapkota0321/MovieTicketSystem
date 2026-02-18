import axios from "axios";

const API_BASE =
  import.meta.env.VITE_BASE_URL?.replace(/\/$/, "") || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    Accept: "application/json",
  },
  withCredentials: true,
});

export default api;
