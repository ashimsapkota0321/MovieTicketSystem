const AUTH_STORAGE_KEY = "mt_auth";
const TOKEN_STORAGE_KEY = "mt_access_token";

const KNOWN_ROLES = ["admin", "vendor", "customer"];
const ROLE_DATA_KEY = {
  admin: "admin",
  vendor: "vendor",
  customer: "user",
};

function normalizeRole(value) {
  const role = String(value || "").trim().toLowerCase();
  return KNOWN_ROLES.includes(role) ? role : "";
}

function authKeyForRole(role) {
  const normalized = normalizeRole(role);
  return normalized ? `${AUTH_STORAGE_KEY}_${normalized}` : AUTH_STORAGE_KEY;
}

function tokenKeyForRole(role) {
  const normalized = normalizeRole(role);
  return normalized ? `${TOKEN_STORAGE_KEY}_${normalized}` : TOKEN_STORAGE_KEY;
}

function safeParse(value) {
  if (!value) return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function getLocalStorage() {
  if (typeof window === "undefined") return null;
  return window.localStorage;
}

function getSessionStorage() {
  if (typeof window === "undefined") return null;
  return window.sessionStorage;
}

export function getRoleFromPath(pathname = "") {
  const path = String(pathname || "").trim().toLowerCase();
  if (path.startsWith("/admin")) return "admin";
  if (path.startsWith("/vendor")) return "vendor";
  return "customer";
}

function readAuthPayload(storage, roleHint = "") {
  if (!storage) return null;

  const normalizedRole = normalizeRole(roleHint);
  const roleAuthKey = authKeyForRole(normalizedRole);
  const roleTokenKey = tokenKeyForRole(normalizedRole);

  // 1) Prefer role-scoped payloads (supports multiple roles logged in at once).
  const parsed = safeParse(storage.getItem(roleAuthKey));
  if (parsed && typeof parsed === "object") {
    const token =
      String(parsed.token || "").trim() || String(storage.getItem(roleTokenKey) || "").trim();
    if (normalizedRole) return { role: normalizedRole, token };
    const roleFromPayload = normalizeRole(parsed.role);
    if (roleFromPayload) return { role: roleFromPayload, token };
  }

  // 2) Backward-compat: legacy single-session keys.
  const legacy = safeParse(storage.getItem(AUTH_STORAGE_KEY));
  if (!legacy || typeof legacy !== "object") return null;
  const legacyRole = normalizeRole(legacy.role);
  if (!legacyRole) return null;
  if (normalizedRole && legacyRole !== normalizedRole) return null;
  const token =
    String(legacy.token || "").trim() || String(storage.getItem(TOKEN_STORAGE_KEY) || "").trim();
  return { role: normalizedRole || legacyRole, token };
}

function inferLegacyRole(localStorageRef, sessionStorageRef) {
  if (sessionStorageRef?.getItem("vendor")) return "vendor";
  if (localStorageRef?.getItem("admin")) return "admin";
  if (localStorageRef?.getItem("user")) return "customer";
  return "";
}

export function getAuthSession(roleHint = "") {
  const localStorageRef = getLocalStorage();
  const sessionStorageRef = getSessionStorage();

  const normalizedRole =
    normalizeRole(roleHint) ||
    (typeof window !== "undefined" ? getRoleFromPath(window.location?.pathname) : "");
  if (!normalizedRole) return null;

  const sessionAuth = readAuthPayload(sessionStorageRef, normalizedRole);
  if (sessionAuth) return { ...sessionAuth, scope: "session" };

  const localAuth = readAuthPayload(localStorageRef, normalizedRole);
  if (localAuth) return { ...localAuth, scope: "local" };

  // Backward-compat for older role info storage (admin/user/vendor objects).
  const legacyRole = inferLegacyRole(localStorageRef, sessionStorageRef);
  if (!legacyRole) return null;
  if (legacyRole !== normalizedRole) return null;
  const token =
    String(sessionStorageRef?.getItem(tokenKeyForRole(normalizedRole)) || "").trim() ||
    String(localStorageRef?.getItem(tokenKeyForRole(normalizedRole)) || "").trim() ||
    String(sessionStorageRef?.getItem(TOKEN_STORAGE_KEY) || "").trim() ||
    String(localStorageRef?.getItem(TOKEN_STORAGE_KEY) || "").trim();
  return { role: normalizedRole, token, scope: sessionStorageRef ? "session" : "local" };
}

export function getAuthToken(roleHint = "") {
  return getAuthSession(roleHint)?.token || "";
}

export function getAuthHeaders(roleHint = "") {
  const token = getAuthToken(roleHint);
  if (!token) return {};
  return {
    Authorization: `Bearer ${token}`,
  };
}

export function storeAuthSession(role, token = "", options = {}) {
  const normalizedRole = normalizeRole(role);
  if (!normalizedRole) return;

  const scope = options?.scope === "session" ? "session" : "local";
  const payload = { role: normalizedRole, token: String(token || "").trim() };
  const localStorageRef = getLocalStorage();
  const sessionStorageRef = getSessionStorage();
  const targetStorage = scope === "session" ? sessionStorageRef : localStorageRef;
  if (!targetStorage) return;

  targetStorage.setItem(authKeyForRole(normalizedRole), JSON.stringify(payload));
  if (payload.token) {
    targetStorage.setItem(tokenKeyForRole(normalizedRole), payload.token);
  }
}

export function clearAuthSession(options = {}) {
  const role = normalizeRole(options?.role);
  const scope = options?.scope || "both"; // "session" | "local" | "both"
  const localStorageRef = getLocalStorage();
  const sessionStorageRef = getSessionStorage();
  const storages = [];
  if (scope === "session" || scope === "both") storages.push(sessionStorageRef);
  if (scope === "local" || scope === "both") storages.push(localStorageRef);

  storages.forEach((storage) => {
    if (!storage) return;

    if (role) {
      storage.removeItem(authKeyForRole(role));
      storage.removeItem(tokenKeyForRole(role));
      return;
    }

    // No role specified: clear everything (including legacy keys).
    storage.removeItem(AUTH_STORAGE_KEY);
    storage.removeItem(TOKEN_STORAGE_KEY);
    KNOWN_ROLES.forEach((r) => {
      storage.removeItem(authKeyForRole(r));
      storage.removeItem(tokenKeyForRole(r));
    });
  });
}

export function getStoredRoleData(role, options = {}) {
  const normalizedRole = normalizeRole(role);
  const key = ROLE_DATA_KEY[normalizedRole];
  if (!key) return null;

  const localStorageRef = getLocalStorage();
  const sessionStorageRef = getSessionStorage();
  const scope = options?.scope || "any"; // "session" | "local" | "any"

  const readFrom = (storage) => {
    if (!storage) return null;
    const raw = storage.getItem(key);
    return safeParse(raw);
  };

  if (scope === "session") return readFrom(sessionStorageRef);
  if (scope === "local") return readFrom(localStorageRef);

  return readFrom(sessionStorageRef) || readFrom(localStorageRef);
}

export function storeRoleData(role, data, options = {}) {
  const normalizedRole = normalizeRole(role);
  const key = ROLE_DATA_KEY[normalizedRole];
  if (!key) return;

  const scope = options?.scope === "session" ? "session" : "local";
  const localStorageRef = getLocalStorage();
  const sessionStorageRef = getSessionStorage();
  const targetStorage = scope === "session" ? sessionStorageRef : localStorageRef;
  if (!targetStorage) return;
  targetStorage.setItem(key, JSON.stringify(data));
}

export function clearStoredRoleData(role = "", options = {}) {
  const localStorageRef = getLocalStorage();
  const sessionStorageRef = getSessionStorage();
  const normalizedRole = normalizeRole(role);
  const scope = options?.scope || "both"; // "session" | "local" | "both"

  const storages = [];
  if (scope === "session" || scope === "both") storages.push(sessionStorageRef);
  if (scope === "local" || scope === "both") storages.push(localStorageRef);

  storages.forEach((storage) => {
    if (!storage) return;
    if (normalizedRole) {
      const key = ROLE_DATA_KEY[normalizedRole];
      if (key) storage.removeItem(key);
      return;
    }
    Object.values(ROLE_DATA_KEY).forEach((key) => storage.removeItem(key));
  });
}

export function getVendorSessionData(options = {}) {
  return getStoredRoleData("vendor", options) || null;
}

export function getVendorStaffRole(options = {}) {
  const vendor = getVendorSessionData(options);
  const role =
    vendor?.staff_role ||
    vendor?.vendor_staff?.role ||
    vendor?.staff?.role ||
    "";
  return String(role || "").trim().toUpperCase();
}

export function isVendorOwner(options = {}) {
  return !getVendorStaffRole(options);
}

export function canAccessVendorFeature(feature, options = {}) {
  const key = String(feature || "").trim().toLowerCase();
  if (!key) return false;
  if (isVendorOwner(options)) return true;

  const staffRole = getVendorStaffRole(options);
  const cashierFeatures = new Set(["bookings", "ticket-validation", "profile"]);
  const managerFeatures = new Set([
    "bookings",
    "ticket-validation",
    "profile",
    "pricing",
    "campaigns-promos",
  ]);

  if (staffRole === "MANAGER") {
    return managerFeatures.has(key);
  }
  if (staffRole === "CASHIER") {
    return cashierFeatures.has(key);
  }
  return false;
}
