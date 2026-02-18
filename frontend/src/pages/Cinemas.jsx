import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import "../css/cinemas.css";
import { cinemaVendors, setRuntimeCinemas } from "../lib/cinemas";

const API_BASE_URL = "http://localhost:8000/api";
const ACCENT_PALETTE = [
  "#00b3ff",
  "#ff8a00",
  "#22c55e",
  "#ec4899",
  "#f97316",
  "#38bdf8",
  "#a855f7",
  "#14b8a6",
];

export default function Cinemas() {
  const navigate = useNavigate();
  const [vendors, setVendors] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let isMounted = true;

    const fetchVendors = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/cinemas/`);
        if (!response.ok) {
          throw new Error("Failed to load cinemas");
        }
        const data = await response.json();
        const normalized = normalizeVendors(data?.vendors, ACCENT_PALETTE);
        if (isMounted) {
          setVendors(normalized);
          setRuntimeCinemas(normalized);
          setError("");
        }
      } catch (err) {
        const fallback = normalizeVendors(cinemaVendors, ACCENT_PALETTE);
        if (isMounted) {
          setVendors(fallback);
          setRuntimeCinemas(fallback);
          setError("Unable to load cinemas from the server.");
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    fetchVendors();
    return () => {
      isMounted = false;
    };
  }, []);

  const visibleVendors = useMemo(() => vendors.filter(Boolean), [vendors]);

  return (
    <div className="wf2-page cinemas-page">
      <div className="wf2-container cinemas-wrap">
        <div className="cinemas-head">
          <div>
            <h2 className="cinemas-title">Choose Your Cinema</h2>
            <p className="cinemas-sub">
              Pick a cinema vendor to see showtimes for that hall.
            </p>
          </div>
        </div>

        <div className="cinemas-grid">
          {visibleVendors.map((vendor) => {
            const badgeText = vendor.city || vendor.theatre || "Now Showing";
            const locationLine = resolveLocationLine(vendor);
            return (
              <button
                key={vendor.slug}
                className="cinema-card"
                type="button"
                style={{ "--cinema-accent": vendor.accent }}
                onClick={() => navigate(`/cinemas/${vendor.slug}`)}
              >
                <div className="cinema-cardTop">
                  <div className="cinema-avatar">
                    {vendor.profile_image ? (
                      <img src={vendor.profile_image} alt={vendor.name} />
                    ) : (
                      <span>{vendor.short}</span>
                    )}
                  </div>
                  <span className="cinema-count">{badgeText}</span>
                </div>
                <div className="cinema-name">{vendor.name}</div>
                <div className="cinema-locations">{locationLine}</div>
                <div className="cinema-action">View schedules</div>
              </button>
            );
          })}
          {isLoading ? (
            <div className="cinemas-empty">Loading cinemas...</div>
          ) : null}
          {!isLoading && !visibleVendors.length ? (
            <div className="cinemas-empty">No cinemas available yet.</div>
          ) : null}
        </div>
        {error ? <div className="cinemas-error">{error}</div> : null}
      </div>
    </div>
  );
}

function normalizeVendors(vendors, palette) {
  const list = Array.isArray(vendors) ? vendors : [];
  return list.map((vendor, index) => {
    const name = String(
      vendor?.name || vendor?.theatre || vendor?.city || `Cinema ${index + 1}`
    ).trim();
    const slug = vendor?.slug || slugify(name) || `cinema-${vendor?.id || index + 1}`;
    const short = vendor?.short || shortLabel(name);
    const accent = vendor?.accent || palette[index % palette.length];
    return {
      ...vendor,
      name,
      slug,
      short,
      accent,
    };
  });
}

function slugify(value) {
  return String(value || "")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

function shortLabel(value) {
  const words = String(value || "")
    .toUpperCase()
    .match(/[A-Z0-9]+/g);
  if (!words || !words.length) return "CIN";
  if (words.length === 1) return words[0].slice(0, 3);
  return words.slice(0, 3).map((word) => word[0]).join("");
}

function resolveLocationLine(vendor) {
  if (Array.isArray(vendor?.locations) && vendor.locations.length) {
    return vendor.locations.slice(0, 3).join(" - ");
  }
  const parts = [vendor?.theatre, vendor?.city].filter(Boolean);
  return parts.length ? parts.join(" - ") : "Cinema hall";
}
