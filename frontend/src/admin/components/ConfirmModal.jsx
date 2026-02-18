import AdminModal from "./AdminModal";

export default function ConfirmModal({ show, title, description, onCancel, onConfirm }) {
  return (
    <AdminModal
      show={show}
      title={title}
      onClose={onCancel}
      footer={
        <>
          <button type="button" className="btn btn-outline-light" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn btn-danger" onClick={onConfirm}>
            Confirm
          </button>
        </>
      }
    >
      <p className="text-muted mb-0">{description}</p>
    </AdminModal>
  );
}
