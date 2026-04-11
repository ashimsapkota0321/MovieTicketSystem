function normalizeBase(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function normalizeHostForLocal(base) {
  if (!base) return "";
  try {
    const parsed = new URL(base);
    if (parsed.hostname === "localhost") {
      parsed.hostname = "127.0.0.1";
    }
    return normalizeBase(parsed.toString());
  } catch {
    return normalizeBase(base).replace(
      /^http:\/\/localhost(?=[:/]|$)/i,
      "http://127.0.0.1"
    );
  }
}

export function resolveApiBase() {
  if (import.meta.env.DEV) {
    // In dev we prefer same-origin calls ("/api") so Vite proxy handles backend routing.
    return "";
  }

  const configured = normalizeHostForLocal(
    import.meta.env.VITE_BASE_URL || import.meta.env.VITE_API_BASE_URL
  );
  if (configured) {
    return configured.replace(/\/api$/i, "");
  }

  return "http://127.0.0.1:8000";
}

export const API_BASE = resolveApiBase();
export const API_BASE_URL = `${API_BASE}/api`;
