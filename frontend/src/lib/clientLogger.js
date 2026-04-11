const LOG_BUFFER_KEY = "__MERO_TICKET_CLIENT_LOGS__";
const CLIENT_LOG_LIMIT = 200;
const IS_VERBOSE_ENABLED =
  import.meta.env.DEV ||
  String(import.meta.env.VITE_ENABLE_CLIENT_LOGGING || "")
    .trim()
    .toLowerCase() === "true";

function pushToBuffer(entry) {
  if (typeof window === "undefined") return;

  const currentBuffer = Array.isArray(window[LOG_BUFFER_KEY]) ? window[LOG_BUFFER_KEY] : [];
  currentBuffer.push(entry);
  while (currentBuffer.length > CLIENT_LOG_LIMIT) {
    currentBuffer.shift();
  }
  window[LOG_BUFFER_KEY] = currentBuffer;
}

function emit(level, message, context = {}, { force = false } = {}) {
  if (!force && !IS_VERBOSE_ENABLED) return;

  const entry = {
    ts: new Date().toISOString(),
    level,
    message,
    ...context,
  };
  pushToBuffer(entry);

  if (level === "error") {
    console.error("[MeroTicket]", entry);
    return;
  }
  if (level === "warn") {
    console.warn("[MeroTicket]", entry);
    return;
  }
  console.info("[MeroTicket]", entry);
}

export function logInfo(message, context = {}) {
  emit("info", message, context);
}

export function logWarn(message, context = {}) {
  emit("warn", message, context);
}

export function logError(message, context = {}) {
  emit("error", message, context, { force: true });
}

export function getClientLogBuffer() {
  if (typeof window === "undefined") return [];
  return Array.isArray(window[LOG_BUFFER_KEY]) ? window[LOG_BUFFER_KEY] : [];
}
