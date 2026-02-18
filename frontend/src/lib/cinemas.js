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

let runtimeCinemas = [];

export function setRuntimeCinemas(list) {
  runtimeCinemas = Array.isArray(list) ? list.filter(Boolean) : [];
}

function getCinemaList() {
  const bySlug = new Map();
  runtimeCinemas.forEach((vendor) => {
    if (vendor && vendor.slug) {
      bySlug.set(vendor.slug, vendor);
    }
  });
  cinemaVendors.forEach((vendor) => {
    if (vendor && vendor.slug && !bySlug.has(vendor.slug)) {
      bySlug.set(vendor.slug, vendor);
    }
  });
  return Array.from(bySlug.values());
}

export function getCinemaBySlug(slug) {
  if (!slug) return null;
  return getCinemaList().find((vendor) => vendor.slug === slug) || null;
}

export function getCinemaFallback(index) {
  const list = getCinemaList();
  if (!list.length) return null;
  const safeIndex = Math.abs(index || 0) % list.length;
  return list[safeIndex];
}

export function resolveCinemaSlug(value) {
  if (!value) return "";
  const cleaned = String(value)
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
  if (!cleaned) return "";

  const match = getCinemaList().find(
    (vendor) => cleaned === vendor.slug || cleaned.includes(vendor.slug)
  );
  return match?.slug || cleaned;
}
