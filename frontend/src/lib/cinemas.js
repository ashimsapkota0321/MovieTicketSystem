export const cinemaVendors = [
  {
    name: "QFX Cinemas",
    slug: "qfx",
    short: "QFX",
    locations: ["Labim", "Civil Mall", "Chhaya Center"],
    accent: "#00b3ff",
  },
  {
    name: "FCube Cinemas",
    slug: "fcube",
    short: "FCUBE",
    locations: ["KL Tower", "Jyatha", "Naxal"],
    accent: "#ff8a00",
  },
  {
    name: "Big Movies",
    slug: "big-movies",
    short: "BIG",
    locations: ["City Center", "Bhaktapur"],
    accent: "#22c55e",
  },
  {
    name: "Midtown Cinemas",
    slug: "midtown",
    short: "MID",
    locations: ["Galleria", "Baneshwor"],
    accent: "#ec4899",
  },
  {
    name: "Cine De Chef",
    slug: "cine-de-chef",
    short: "CDC",
    locations: ["Chhaya Center"],
    accent: "#f97316",
  },
  {
    name: "One Cinemas",
    slug: "one-cinemas",
    short: "ONE",
    locations: ["Basundhara", "Koteswor"],
    accent: "#38bdf8",
  },
];

export function getCinemaBySlug(slug) {
  if (!slug) return null;
  return cinemaVendors.find((vendor) => vendor.slug === slug) || null;
}

export function getCinemaFallback(index) {
  if (!cinemaVendors.length) return null;
  const safeIndex = Math.abs(index || 0) % cinemaVendors.length;
  return cinemaVendors[safeIndex];
}

export function resolveCinemaSlug(value) {
  if (!value) return "";
  const cleaned = String(value)
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
  if (!cleaned) return "";

  const match = cinemaVendors.find(
    (vendor) => cleaned === vendor.slug || cleaned.includes(vendor.slug)
  );
  return match?.slug || cleaned;
}
