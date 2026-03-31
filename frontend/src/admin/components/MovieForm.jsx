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
        <label className="form-label">Poster Image</label>
        <input
          type="file"
          className="form-control"
          accept="image/*"
          onChange={(event) => updateField("posterFile", event.target.files?.[0] || null)}
          disabled={loading}
        />
        {value.posterFile ? (
          <small className="text-muted">Selected: {value.posterFile.name}</small>
        ) : value.posterPreview ? (
          <small className="text-muted">Current poster already set.</small>
        ) : null}
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
  const currentImage = credit.photoUrl || "";
  return (
    <div className="border rounded p-3 admin-credit-row">
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
      <div className="row g-2 mt-1 align-items-end">
        <div className="col-md-8">
          <label className="form-label">Image URL (optional)</label>
          <input
            type="url"
            className="form-control"
            placeholder="https://example.com/photo.jpg"
            value={credit.photoUrl || ""}
            onChange={(event) => onChange({ photoUrl: event.target.value })}
            disabled={disabled}
          />
        </div>
        <div className="col-md-4">
          <label className="form-label">Choose Image (optional)</label>
          <input
            type="file"
            className="form-control"
            accept="image/*"
            onChange={(event) =>
              onChange({
                photoFile: event.target.files?.[0] || null,
              })
            }
            disabled={disabled}
          />
        </div>
      </div>
      {credit.photoFile ? (
        <div className="mt-2 text-muted small">Selected image: {credit.photoFile.name}</div>
      ) : currentImage ? (
        <div className="mt-2 text-muted small">Current image is set.</div>
      ) : null}
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
    photoUrl: "",
    photoFile: null,
    position: "",
  };
}
