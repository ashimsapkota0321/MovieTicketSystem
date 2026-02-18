import { createContext, useCallback, useContext, useMemo, useState } from "react";

const AdminToastContext = createContext(null);

export function AdminToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  const pushToast = useCallback((toast) => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const next = {
      id,
      title: toast.title || "Action completed",
      message: toast.message || "Your request has been queued.",
      tone: toast.tone || "info",
    };
    setToasts((prev) => [...prev, next]);
    setTimeout(() => removeToast(id), toast.duration || 3200);
  }, [removeToast]);

  const value = useMemo(() => ({ pushToast }), [pushToast]);

  return (
    <AdminToastContext.Provider value={value}>
      {children}
      <div className="admin-toast-stack">
        {toasts.map((toast) => (
          <div className="admin-toast" key={toast.id}>
            <span className="dot" />
            <div>
              <div className="fw-semibold">{toast.title}</div>
              <div className="text-muted small">{toast.message}</div>
            </div>
          </div>
        ))}
      </div>
    </AdminToastContext.Provider>
  );
}

export function useAdminToast() {
  const context = useContext(AdminToastContext);
  if (!context) {
    return { pushToast: () => {} };
  }
  return context;
}
