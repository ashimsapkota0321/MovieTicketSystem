export default function AdminModal({ show, title, onClose, footer, children }) {
  if (!show) return null;

  return (
    <div className="admin-modal-backdrop" onClick={onClose}>
      <div className="admin-modal" onClick={(event) => event.stopPropagation()}>
        <div className="d-flex align-items-center justify-content-between mb-3">
          <h5 className="mb-0">{title}</h5>
          <button type="button" className="btn btn-sm btn-outline-light" onClick={onClose}>
            Close
          </button>
        </div>
        <div>{children}</div>
        {footer ? <div className="d-flex justify-content-end gap-2 mt-4">{footer}</div> : null}
      </div>
    </div>
  );
}
