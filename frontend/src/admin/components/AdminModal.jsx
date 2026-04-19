export default function AdminModal({ show, title, onClose, footer, children }) {
  if (!show) return null;

  return (
    <div className="admin-modal-backdrop" onClick={onClose} role="presentation">
      <div 
        className="admin-modal" 
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-modal-title"
      >
        <div className="d-flex align-items-center justify-content-between gap-3 mb-4">
          <h5 id="admin-modal-title" className="mb-0">{title}</h5>
          <button 
            type="button" 
            className="btn btn-sm btn-outline-light flex-shrink-0" 
            onClick={onClose}
            aria-label="Close modal"
            title="Close"
          >
            ✕
          </button>
        </div>
        <div className="admin-modal-body">{children}</div>
        {footer ? <div className="d-flex justify-content-end gap-2 mt-4 admin-modal-footer">{footer}</div> : null}
      </div>
    </div>
  );
}
