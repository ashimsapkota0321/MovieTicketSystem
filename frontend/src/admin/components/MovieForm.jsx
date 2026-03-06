import { ExternalLink, Plus, Trash2 } from "lucide-react";

export default function MovieForm({ value, onChange, onEditPerson, loading = false }) {
  const updateField = (field, val) => {
    onChange({ ...value, [field]: val });
  };

  const updateCredit = (type, index, patch) => {
    const list = Array.isArray(value?.[type]) ? [...value[type]] : [];
    list[index] = { ...list[index], ...patch };
    onChange({ ...value, [type]: list });
  };

  const addCredit = (type) => {
    const list = Array.isArray(value?.[type]) ? [...value[type]] : [];
    list.push(buildEmptyCredit(type));
    onChange({ ...value, [type]: list });
  };

  const removeCredit = (type, index) => {
    const list = Array.isArray(value?.[type]) ? [...value[type]] : [];
    list.splice(index, 1);
    onChange({ ...value, [type]: list });
  };

  return (
    <div className="row g-3">
      <div className="col-md-8">
        <label className="form-label">Movie title</label>
        <input
          className="form-control"
          value={value.title}
          onChange={(event) => updateField("title", event.target.value)}
          disabled={loading}
        />
      </div>
      <div className="col-md-4">
        <label className="form-label">Duration</label>
        <input
          className="form-control"
          value={value.duration}
          onChange={(event) => updateField("duration", event.target.value)}
          disabled={loading}
        />
      </div>
      <div className="col-md-6">
        <label className="form-label">Genre</label>
        <input
          className="form-control"
          value={value.genre}
          onChange={(event) => updateField("genre", event.target.value)}
          disabled={loading}
        />
      </div>
      <div className="col-md-6">
        <label className="form-label">Language</label>
        <input
          className="form-control"
          value={value.language}
          onChange={(event) => updateField("language", event.target.value)}
          disabled={loading}
        />
      </div>
      <div className="col-md-4">
        <label className="form-label">Rating (certificate)</label>
        <input
          className="form-control"
          value={value.rating}
          onChange={(event) => updateField("rating", event.target.value)}
          disabled={loading}
        />
      </div>
      <div className="col-md-4">
        <label className="form-label">Release date</label>
        <input
          type="date"
          className="form-control"
          value={value.releaseDate}
          onChange={(event) => updateField("releaseDate", event.target.value)}
          disabled={loading}
        />
      </div>
      <div className="col-md-4">
        <label className="form-label">Status</label>
        <select
          className="form-select"
          value={value.status}
          onChange={(event) => updateField("status", event.target.value)}
          disabled={loading}
        >
          <option value="NOW_SHOWING">Now Showing</option>
          <option value="COMING_SOON">Coming Soon</option>
        </select>
      </div>
      <div className="col-12">
        <label className="form-label">Synopsis</label>
        <textarea
          className="form-control"
          rows="3"
          placeholder="Short plot summary"
          value={value.synopsis}
          onChange={(event) => updateField("synopsis", event.target.value)}
          disabled={loading}
        />
      </div>
      <div className="col-md-6">
        <label className="form-label">Poster URL</label>
        <input
          className="form-control"
          value={value.posterUrl}
          onChange={(event) => updateField("posterUrl", event.target.value)}
          disabled={loading}
        />
      </div>
      <div className="col-md-6">
        <label className="form-label">Trailer URL</label>
        <input
          className="form-control"
          value={value.trailerUrl}
          onChange={(event) => updateField("trailerUrl", event.target.value)}
          disabled={loading}
        />
      </div>

      <div className="col-12 mt-3">
        <div className="d-flex align-items-center justify-content-between">
          <h5 className="mb-0">Cast</h5>
          <button
            type="button"
            className="btn btn-outline-light btn-sm"
            onClick={() => addCredit("cast")}
            disabled={loading}
          >
            <Plus size={14} className="me-1" /> Add Cast
          </button>
        </div>
        <div className="mt-2 d-flex flex-column gap-3">
          {(value.cast || []).map((credit, index) => (
            <CreditRow
              key={`cast-${index}`}
              credit={credit}
              type="CAST"
              onChange={(patch) => updateCredit("cast", index, patch)}
              onRemove={() => removeCredit("cast", index)}
              disabled={loading}
              onEditPerson={() => onEditPerson?.(credit.personId)}
            />
          ))}
          {!value.cast?.length ? <div className="text-muted small">No cast added.</div> : null}
        </div>
      </div>

      <div className="col-12 mt-3">
        <div className="d-flex align-items-center justify-content-between">
          <h5 className="mb-0">Crew</h5>
          <button
            type="button"
            className="btn btn-outline-light btn-sm"
            onClick={() => addCredit("crew")}
            disabled={loading}
          >
            <Plus size={14} className="me-1" /> Add Crew
          </button>
        </div>
        <div className="mt-2 d-flex flex-column gap-3">
          {(value.crew || []).map((credit, index) => (
            <CreditRow
              key={`crew-${index}`}
              credit={credit}
              type="CREW"
              onChange={(patch) => updateCredit("crew", index, patch)}
              onRemove={() => removeCredit("crew", index)}
              disabled={loading}
              onEditPerson={() => onEditPerson?.(credit.personId)}
            />
          ))}
          {!value.crew?.length ? <div className="text-muted small">No crew added.</div> : null}
        </div>
      </div>
    </div>
  );
}

function CreditRow({ credit, type, onChange, onRemove, disabled, onEditPerson }) {
  const roleLabel = type === "CAST" ? "Role (character name)" : "Role (job title)";
  return (
    <div className="border rounded p-3 bg-dark bg-opacity-25">
      <div className="row g-2 align-items-end">
        <div className="col-md-5">
          <label className="form-label">Name</label>
          <input
            className="form-control"
            value={credit.name || ""}
            onChange={(event) =>
              onChange({ name: event.target.value, personId: "" })
            }
            disabled={disabled}
          />
        </div>
        <div className="col-md-5">
          <label className="form-label">{roleLabel}</label>
          <input
            className="form-control"
            value={credit.role || ""}
            onChange={(event) => onChange({ role: event.target.value })}
            disabled={disabled}
          />
        </div>
        <div className="col-md-2 text-end">
          <button
            type="button"
            className="btn btn-outline-danger btn-sm"
            onClick={onRemove}
            disabled={disabled}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>
      {credit.personId ? (
        <button
          type="button"
          className="btn btn-link btn-sm mt-2"
          onClick={onEditPerson}
          disabled={disabled}
        >
          <ExternalLink size={12} className="me-1" />
          Edit details
        </button>
      ) : (
        <div className="mt-2 text-muted small">Save movie to edit details.</div>
      )}
    </div>
  );
}

function buildEmptyCredit(type) {
  return {
    roleType: type,
    personId: "",
    name: "",
    role: "",
    position: "",
  };
}
