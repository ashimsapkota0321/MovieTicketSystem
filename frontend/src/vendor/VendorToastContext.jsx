import { createContext, useCallback, useContext, useMemo, useState } from "react";

const VendorToastContext = createContext(null);

function normalizeTone(value) {
  const tone = String(value || "").trim().toLowerCase();
  if (["success", "error", "warning", "info"].includes(tone)) {
    return tone;
  }
  return "info";
}

function inferTone(toast) {
  const explicit = normalizeTone(toast?.tone);
  if (explicit !== "info") return explicit;
  const text = `${toast?.title || ""} ${toast?.message || ""}`.toLowerCase();
  if (/error|fail|failed|unable|invalid|denied|missing/.test(text)) return "error";
  if (/warn|warning|caution|retry|expir/.test(text)) return "warning";
  if (/success|saved|updated|created|deleted|completed|done/.test(text)) return "success";
  return "info";
}

function toneIcon(tone) {
  if (tone === "success") return "✓";
  if (tone === "error") return "✕";
  if (tone === "warning") return "!";
  return "i";
}

export function VendorToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const pushToast = useCallback((toast) => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const tone = inferTone(toast);
    const next = {
      id,
      title: toast?.title || "Action completed",
      message: toast?.message || "Your request has been queued.",
      tone,
      icon: toneIcon(tone),
    };
    setToasts((prev) => [...prev, next]);
    setTimeout(() => removeToast(id), toast?.duration || 3200);
  }, [removeToast]);

  const value = useMemo(() => ({ pushToast }), [pushToast]);

  return (
    <VendorToastContext.Provider value={value}>
      {children}
      <div className="vendor-toast-stack">
        {toasts.map((toast) => (
          <div className={`vendor-toast vendor-toast-${toast.tone}`} key={toast.id} role="status" aria-live="polite">
            <span className="vendor-toast-icon" aria-hidden="true">{toast.icon}</span>
            <div className="vendor-toast-content">
              <div className="vendor-toast-title">{toast.title}</div>
              <div className="vendor-toast-message">{toast.message}</div>
            </div>
            <button
              type="button"
              className="vendor-toast-close"
              aria-label="Dismiss notification"
              onClick={() => removeToast(toast.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </VendorToastContext.Provider>
  );
}

export function useVendorToast() {
  const context = useContext(VendorToastContext);
  if (!context) {
    return { pushToast: () => {} };
  }
  return context;
}
