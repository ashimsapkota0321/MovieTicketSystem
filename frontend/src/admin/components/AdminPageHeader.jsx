export default function AdminPageHeader({ title, subtitle, children }) {
  return (
    <div className="d-flex flex-wrap align-items-center justify-content-between gap-3">
      <div>
        <h2 className="mb-1">{title}</h2>
        {subtitle ? <p className="text-muted mb-0">{subtitle}</p> : null}
      </div>
      <div className="d-flex align-items-center gap-2 flex-wrap">{children}</div>
    </div>
  );
}
