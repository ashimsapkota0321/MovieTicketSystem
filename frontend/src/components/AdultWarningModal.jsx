import React from "react";
import "../css/adultWarning.css";

export default function AdultWarningModal({
  open,
  title = "Adult",
  minAge = 16,
  onCancel,
  onConfirm,
}) {
  if (!open) return null;

  return (
    <div
      className="wf2-adultOverlay"
      role="dialog"
      aria-modal="true"
      aria-label="Adult content warning"
      onClick={onCancel}
    >
      <div className="wf2-adultModal" onClick={(event) => event.stopPropagation()}>
        <div className="wf2-adultHeader">
          <span className="wf2-adultBadge">18+</span>
          <h3>{title}</h3>
        </div>
        <p>
          This movie has been rated <strong>[A]</strong> and is for audiences above the age
          of <strong> {minAge}</strong>.
        </p>
        <p>Please carry a valid photo ID/age proof to the theatre.</p>
        <p>No refund of tickets once bought.</p>
        <div className="wf2-adultActions">
          <button type="button" className="wf2-adultBtn wf2-adultBtnGhost" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="wf2-adultBtn wf2-adultBtnPrimary" onClick={onConfirm}>
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}
