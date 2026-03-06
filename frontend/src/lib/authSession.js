const AUTH_STORAGE_KEY = "mt_auth";
const TOKEN_STORAGE_KEY = "mt_access_token";

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

function readAuthPayload(storage) {
  if (!storage) return null;
  const parsed = safeParse(storage.getItem(AUTH_STORAGE_KEY));
  if (!parsed || typeof parsed !== "object") return null;
  const role = String(parsed.role || "").trim().toLowerCase();
  if (!role) return null;
  const token =
    String(parsed.token || "").trim() ||
    String(storage.getItem(TOKEN_STORAGE_KEY) || "").trim();
  return { role, token };
}

function inferLegacyRole(localStorageRef, sessionStorageRef) {
  if (sessionStorageRef?.getItem("vendor")) return "vendor";
  if (localStorageRef?.getItem("admin")) return "admin";
  if (localStorageRef?.getItem("user")) return "customer";
  return "";
}

export function getAuthSession() {
  const localStorageRef = getLocalStorage();
  const sessionStorageRef = getSessionStorage();

  const sessionAuth = readAuthPayload(sessionStorageRef);
  if (sessionAuth) return sessionAuth;

  const localAuth = readAuthPayload(localStorageRef);
  if (localAuth) return localAuth;

  const legacyRole = inferLegacyRole(localStorageRef, sessionStorageRef);
  if (!legacyRole) return null;
  const token =
    String(sessionStorageRef?.getItem(TOKEN_STORAGE_KEY) || "").trim() ||
    String(localStorageRef?.getItem(TOKEN_STORAGE_KEY) || "").trim();
  return { role: legacyRole, token };
}

export function getAuthToken() {
  return getAuthSession()?.token || "";
}

export function getAuthHeaders() {
  const token = getAuthToken();
  if (!token) return {};
  return {
    Authorization: `Bearer ${token}`,
  };
}

export function storeAuthSession(role, token = "") {
  const normalizedRole = String(role || "").trim().toLowerCase();
  if (!normalizedRole) return;

  clearAuthSession();
  const payload = { role: normalizedRole, token: String(token || "").trim() };
  const localStorageRef = getLocalStorage();
  const sessionStorageRef = getSessionStorage();
  const targetStorage =
    normalizedRole === "vendor" ? sessionStorageRef : localStorageRef;
  if (!targetStorage) return;

  targetStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(payload));
  if (payload.token) {
    targetStorage.setItem(TOKEN_STORAGE_KEY, payload.token);
  }
}

export function clearAuthSession() {
  const localStorageRef = getLocalStorage();
  const sessionStorageRef = getSessionStorage();
  [localStorageRef, sessionStorageRef].forEach((storage) => {
    if (!storage) return;
    storage.removeItem(AUTH_STORAGE_KEY);
    storage.removeItem(TOKEN_STORAGE_KEY);
  });
}

export function clearStoredRoleData() {
  const localStorageRef = getLocalStorage();
  const sessionStorageRef = getSessionStorage();
  localStorageRef?.removeItem("admin");
  localStorageRef?.removeItem("user");
  sessionStorageRef?.removeItem("vendor");
}
