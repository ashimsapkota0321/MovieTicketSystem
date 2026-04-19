import React, { useEffect, useState } from "react";
import Pagination from "../components/Pagination";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import {
  AtSign,
  Calendar,
  Camera,
  Check,
  LogOut,
  Mail,
  Pencil,
  Phone,
} from "lucide-react";
import "../css/profile.css";
import {
  clearAuthSession,
  clearStoredRoleData,
  getAuthHeaders,
  getAuthSession,
  getStoredRoleData,
  storeRoleData,
} from "../lib/authSession";
import { fetchCustomerBookingHistory } from "../lib/catalogApi";
import { API_BASE_URL } from "../lib/apiBase";

const EMPTY_PROFILE = {
  first_name: "",
  middle_name: "",
  last_name: "",
  email: "",
  phone_number: "",
  dob: "",
  avatar: "",
  username: "",
};

const getStoredUser = () => {
  return getStoredRoleData("customer");
};

const getDefaultUsername = (user) => {
  if (!user) return "";
  if (user.username) return user.username;
  if (user.email) return user.email.split("@")[0];
  if (user.phone_number) return user.phone_number;
  if (user.phone) return user.phone;
  return "";
};

const getDisplayName = (profile) => {
  if (!profile) return "";
  const nameParts = [
    profile.first_name,
    profile.middle_name,
    profile.last_name,
  ].filter(Boolean);
  if (nameParts.length) return nameParts.join(" ");
  if (profile.name) return profile.name;
  if (profile.username) return profile.username;
  if (profile.email) return profile.email;
  if (profile.phone_number) return profile.phone_number;
  if (profile.phone) return profile.phone;
  return "";
};

const getInitials = (name) => {
  const trimmed = String(name || "").trim();
  if (!trimmed) return "MT";
  const parts = trimmed.split(/\s+/);
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  return parts
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
};

const formatValue = (value) => {
  if (value === 0) return "0";
  const trimmed = String(value ?? "").trim();
  return trimmed ? trimmed : "Not set";
};

const revokePreviewUrl = (url) => {
  if (url && url.startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
};

const buildUpdatePayload = (profile) => {
  const payload = {};
  const firstName = String(profile.first_name ?? "").trim();
  const middleName = String(profile.middle_name ?? "").trim();
  const lastName = String(profile.last_name ?? "").trim();
  const dob = String(profile.dob ?? "").trim();

  if (firstName) payload.first_name = firstName;
  if (middleName) payload.middle_name = middleName;
  if (lastName) payload.last_name = lastName;
  if (dob) payload.dob = dob;

  return payload;
};

const deriveProfile = (user) => ({
  ...EMPTY_PROFILE,
  first_name: user?.first_name || user?.firstName || "",
  middle_name: user?.middle_name || user?.middleName || "",
  last_name: user?.last_name || user?.lastName || "",
  email: user?.email || "",
  phone_number: user?.phone_number || user?.phone || "",
  dob: user?.dob || user?.date_of_birth || user?.birth_date || "",
  avatar:
    user?.avatar ||
    user?.avatarUrl ||
    user?.profile_image ||
    user?.profileImage ||
    user?.photo ||
    user?.image ||
    "",
  username: user?.username || getDefaultUsername(user),
});

export default function Profile() {
  const navigate = useNavigate();
  const [user, setUser] = useState(() => getStoredUser());
  const [formData, setFormData] = useState(() =>
    deriveProfile(getStoredUser())
  );
  const [status, setStatus] = useState(null);
  const [isEditing, setIsEditing] = useState(false);
  const [avatarFile, setAvatarFile] = useState(null);
  const [removeAvatar, setRemoveAvatar] = useState(false);
  const [isImageOpen, setImageOpen] = useState(false);
  const [bookingHistory, setBookingHistory] = useState([]);
  const [historyPage, setHistoryPage] = useState(1);
  const HISTORY_PAGE_SIZE = 10;
  const [bookingHistoryLoading, setBookingHistoryLoading] = useState(false);
  const [bookingHistoryError, setBookingHistoryError] = useState("");

  useEffect(() => {
    if (!user) {
      navigate("/login");
    }
  }, [user, navigate]);

  useEffect(() => {
    if (user) {
      setFormData(deriveProfile(user));
    }
  }, [user]);

  useEffect(() => {
    let active = true;

    const loadBookingHistory = async () => {
      if (!user) {
        setBookingHistory([]);
        return;
      }
      setBookingHistoryLoading(true);
      setBookingHistoryError("");
      try {
        const history = await fetchCustomerBookingHistory();
        if (!active) return;
        setBookingHistory(Array.isArray(history) ? history : []);
      } catch (err) {
        if (!active) return;
        setBookingHistory([]);
        setBookingHistoryError(err.message || "Unable to load booking history.");
      } finally {
        if (active) setBookingHistoryLoading(false);
      }
    };

    loadBookingHistory();
    return () => {
      active = false;
    };
  }, [user]);

  useEffect(() => {
    if (!status || status.type !== "success") return;
    const timer = setTimeout(() => setStatus(null), 2000);
    return () => clearTimeout(timer);
  }, [status]);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleAvatarChange = (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setStatus({ type: "error", message: "Please select an image file." });
      event.target.value = "";
      return;
    }
    revokePreviewUrl(formData.avatar);
    const previewUrl = URL.createObjectURL(file);
    setFormData((prev) => ({ ...prev, avatar: previewUrl }));
    setAvatarFile(file);
    setRemoveAvatar(false);
    setStatus(null);
    setIsEditing(true);
    event.target.value = "";
  };

  const handleRemoveAvatar = () => {
    if (!formData.avatar) return;
    revokePreviewUrl(formData.avatar);
    setFormData((prev) => ({ ...prev, avatar: "" }));
    setAvatarFile(null);
    setRemoveAvatar(true);
    setStatus(null);
    setIsEditing(true);
  };

  const handleEditToggle = () => {
    if (!isEditing) {
      setIsEditing(true);
      setStatus(null);
    }
  };

  const handleCancel = () => {
    revokePreviewUrl(formData.avatar);
    setFormData(deriveProfile(user));
    setAvatarFile(null);
    setRemoveAvatar(false);
    setIsEditing(false);
    setStatus(null);
  };

  const handleAvatarOpen = () => {
    if (!formData.avatar) return;
    setImageOpen(true);
  };

  const handleAvatarClose = () => {
    setImageOpen(false);
  };

  const handleSave = async (event) => {
    if (event) event.preventDefault();
    if (!user || !isEditing) return;

    const firstName = String(formData.first_name ?? "").trim();
    const lastName = String(formData.last_name ?? "").trim();
    if (!firstName || !lastName) {
      setStatus({
        type: "error",
        message: "First name and last name are required.",
      });
      return;
    }

    if (!user?.id) {
      setStatus({
        type: "error",
        message: "User ID missing. Please log in again.",
      });
      return;
    }

    const payload = buildUpdatePayload(formData);
    const hasAvatarChange = Boolean(avatarFile) || removeAvatar;
    if (!Object.keys(payload).length && !hasAvatarChange) {
      setStatus({
        type: "error",
        message: "No profile changes to update.",
      });
      return;
    }

    try {
      const requestOptions = {
        method: "PATCH",
        headers: {
          Accept: "application/json",
          ...getAuthHeaders(),
        },
      };

      if (hasAvatarChange) {
        const formPayload = new FormData();
        Object.entries(payload).forEach(([key, value]) => {
          formPayload.append(key, value);
        });
        if (avatarFile) {
          formPayload.append("profile_image", avatarFile);
        }
        if (removeAvatar) {
          formPayload.append("remove_avatar", "true");
        }
        requestOptions.body = formPayload;
      } else {
        requestOptions.headers["Content-Type"] = "application/json";
        requestOptions.body = JSON.stringify(payload);
      }

      const response = await fetch(
        `${API_BASE_URL}/profile/${user.id}/`,
        requestOptions
      );

      let data = null;
      try {
        data = await response.json();
      } catch (parseErr) {
        console.error("Failed to parse JSON:", parseErr);
      }

      if (!response.ok) {
        const errorMessage =
          (data && (data.message || data.error)) ||
          `Server error: ${response.status}`;
        throw new Error(errorMessage);
      }

      const { avatar, ...formFields } = formData;
      const updatedUser = {
        ...user,
        ...formFields,
        ...(data && data.user ? data.user : {}),
        email: user?.email ?? formData.email,
        phone_number: user?.phone_number ?? formData.phone_number,
        phone: user?.phone ?? user?.phone_number ?? formData.phone_number,
      };

      revokePreviewUrl(formData.avatar);
      const auth = getAuthSession("customer");
      const scope = auth?.scope === "session" ? "session" : "local";
      storeRoleData("customer", updatedUser, { scope });
      setUser(updatedUser);
      setFormData(deriveProfile(updatedUser));
      setAvatarFile(null);
      setRemoveAvatar(false);
      setIsEditing(false);
      setStatus({ type: "success", message: "Profile updated." });
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("mt:user-updated"));
      }
    } catch (err) {
      console.error("Profile update error:", err);
      setStatus({
        type: "error",
        message: err.message || "Failed to update profile.",
      });
    }
  };

  const handleLogout = () => {
    const auth = getAuthSession("customer");
    const scope = auth?.scope === "session" ? "session" : "local";
    clearAuthSession({ role: "customer", scope });
    clearStoredRoleData("customer", { scope });
    setUser(null);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event("mt:user-updated"));
    }
    navigate("/login");
  };

  if (!user) return null;

  const displayName = getDisplayName(formData);
  const initials = getInitials(displayName);
  const imageModalMarkup =
    isImageOpen && formData.avatar && typeof document !== "undefined"
      ? createPortal(
          <div
            className="wf2-profileImageModal"
            role="dialog"
            aria-modal="true"
            onClick={handleAvatarClose}
          >
            <div
              className="wf2-profileImageDialog"
              onClick={(event) => event.stopPropagation()}
            >
              <button
                className="wf2-profileImageClose"
                type="button"
                onClick={handleAvatarClose}
                aria-label="Close image"
              >
                ×
              </button>
              <img
                className="wf2-profileImageFull"
                src={formData.avatar}
                alt="Profile full size"
              />
            </div>
          </div>,
          document.body
        )
      : null;

  return (
    <form
      className={`wf2-profilePage ${isEditing ? "wf2-profilePage--editing" : ""}`}
      onSubmit={handleSave}
    >
      <section className="wf2-profileHeader">
        <div className="wf2-profileHeaderMain">
          <div className="wf2-profileAvatarWrap">
            <div
              className={`wf2-profileAvatar ${
                formData.avatar ? "wf2-profileAvatar--clickable" : ""
              }`}
              onClick={handleAvatarOpen}
              role={formData.avatar ? "button" : undefined}
              tabIndex={formData.avatar ? 0 : undefined}
              onKeyDown={(event) => {
                if (!formData.avatar) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  handleAvatarOpen();
                }
              }}
            >
              {formData.avatar ? (
                <img src={formData.avatar} alt="Profile avatar" />
              ) : (
                <span>{initials}</span>
              )}
            </div>
            {isEditing ? (
              <>
                <label className="wf2-profileCamera" title="Change photo">
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleAvatarChange}
                  />
                  <Camera size={16} />
                </label>
                {formData.avatar ? (
                  <button
                    className="wf2-profileRemovePhoto"
                    type="button"
                    onClick={handleRemoveAvatar}
                  >
                    Remove
                  </button>
                ) : null}
              </>
            ) : null}
          </div>

          <div className="wf2-profileHeaderInfo">
            <div className="wf2-profileNameRow">
              <h1 className="wf2-profileName">
                {displayName || "Mero Ticket User"}
              </h1>
              <div className="wf2-profileHeaderActions">
                {!isEditing ? (
                  <>
                    <button
                      className="wf2-profileEditBtn"
                      type="button"
                      onClick={handleEditToggle}
                    >
                      <Pencil size={16} />
                      Edit
                    </button>
                    <button
                      className="wf2-profileLogout"
                      type="button"
                      onClick={handleLogout}
                    >
                      <LogOut size={16} />
                      Logout
                    </button>
                  </>
                ) : null}
              </div>
            </div>

            <div className="wf2-profileMetaRow">
              <span className="wf2-profileMetaItem">
                <AtSign size={14} />
                {formData.username || "mero-user"}
              </span>
            </div>

            {status ? (
              <div
                className={`wf2-profileStatus ${
                  status.type === "success"
                    ? "wf2-profileStatusSuccess"
                    : "wf2-profileStatusError"
                }`}
              >
                {status.message}
              </div>
            ) : null}
          </div>
        </div>
        <div className="wf2-profileHeaderDetails">
          <div className="wf2-profileDetailsHeader">
            <h2 className="wf2-profileDetailsTitle">Profile details</h2>
            <p className="wf2-profileDetailsHint">
              {isEditing
                ? "Update your details and click Update."
                : "Click edit to update your details."}
            </p>
          </div>
          {isEditing ? (
            <>
              <div className="wf2-profileDetailsGrid">
                <label className="wf2-profileField">
                  <span>First name</span>
                  <div className="wf2-profileInputRow">
                    <input
                      className="wf2-profileInput"
                      name="first_name"
                      type="text"
                      value={formData.first_name}
                      onChange={handleChange}
                      readOnly={!isEditing}
                      disabled={!isEditing}
                      placeholder="First name"
                    />
                  </div>
                </label>
                <label className="wf2-profileField">
                  <span>Middle name</span>
                  <div className="wf2-profileInputRow">
                    <input
                      className="wf2-profileInput"
                      name="middle_name"
                      type="text"
                      value={formData.middle_name}
                      onChange={handleChange}
                      readOnly={!isEditing}
                      disabled={!isEditing}
                      placeholder="Middle name"
                    />
                  </div>
                </label>
                <label className="wf2-profileField">
                  <span>Last name</span>
                  <div className="wf2-profileInputRow">
                    <input
                      className="wf2-profileInput"
                      name="last_name"
                      type="text"
                      value={formData.last_name}
                      onChange={handleChange}
                      readOnly={!isEditing}
                      disabled={!isEditing}
                      placeholder="Last name"
                    />
                  </div>
                </label>
                <label className="wf2-profileField">
                  <span>Username (auto)</span>
                  <div className="wf2-profileInputRow wf2-profileInputRowLocked">
                    <AtSign size={16} />
                    <input
                      className="wf2-profileInput"
                      name="username"
                      type="text"
                      value={formData.username}
                      readOnly
                      disabled
                    />
                  </div>
                </label>
                <label className="wf2-profileField">
                  <span>Date of birth</span>
                  <div className="wf2-profileInputRow">
                    <Calendar size={16} />
                    <input
                      className="wf2-profileInput"
                      name="dob"
                      type="date"
                      value={formData.dob}
                      onChange={handleChange}
                      readOnly={!isEditing}
                      disabled={!isEditing}
                    />
                  </div>
                </label>
                <label className="wf2-profileField">
                  <span>Email (locked)</span>
                  <div className="wf2-profileInputRow wf2-profileInputRowLocked">
                    <Mail size={16} />
                    <input
                      className="wf2-profileInput"
                      name="email"
                      type="email"
                      value={formData.email}
                      readOnly
                      disabled
                    />
                  </div>
                </label>
                <label className="wf2-profileField">
                  <span>Phone number (locked)</span>
                  <div className="wf2-profileInputRow wf2-profileInputRowLocked">
                    <Phone size={16} />
                    <input
                      className="wf2-profileInput"
                      name="phone_number"
                      type="tel"
                      value={formData.phone_number}
                      readOnly
                      disabled
                    />
                  </div>
                </label>
              </div>
              <div className="wf2-profileDetailsActions">
                <button
                  className="wf2-profileEditBtn wf2-profileEditBtnSave"
                  type="submit"
                >
                  <Check size={16} />
                  Update
                </button>
                <button
                  className="wf2-profileCancelBtn"
                  type="button"
                  onClick={handleCancel}
                >
                  Cancel
                </button>
              </div>
            </>
          ) : (
            <div className="wf2-profileDetailsGrid">
              <div className="wf2-profileField">
                <span>First name</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.first_name)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Middle name</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.middle_name)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Last name</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.last_name)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Username</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.username)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Date of birth</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.dob)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Email</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.email)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Phone number</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.phone_number)}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="wf2-profileHistory">
        <div className="wf2-profileHistoryHeader">
          <h2>Booking history</h2>
          <p>All your bookings with payment status and amount.</p>
        </div>

        {bookingHistoryError ? (
          <div className="wf2-profileHistoryError">{bookingHistoryError}</div>
        ) : null}

        <div className="wf2-profileHistoryTableWrap">
          <table className="wf2-profileHistoryTable">
            <thead>
              <tr>
                <th>Movie</th>
                <th>Show time</th>
                <th>Seats</th>
                <th>Payment</th>
                <th>Status</th>
                <th>Total</th>
              </tr>
            </thead>
            <tbody>
              {bookingHistory
                .slice((historyPage - 1) * HISTORY_PAGE_SIZE, historyPage * HISTORY_PAGE_SIZE)
                .map((booking) => (
                  <tr key={booking.id}>
                    <td>{booking.movie || "-"}</td>
                    <td>{formatHistoryDateTime(booking.showTime)}</td>
                    <td>{booking.seats || "-"}</td>
                    <td>{formatPaymentCell(booking)}</td>
                    <td>{booking.status || "Pending"}</td>
                    <td>{formatCurrency(booking.total)}</td>
                  </tr>
                ))}
              {!bookingHistoryLoading && bookingHistory.length === 0 ? (
                <tr>
                  <td colSpan="6">No bookings yet.</td>
                </tr>
              ) : null}
              {bookingHistoryLoading ? (
                <tr>
                  <td colSpan="6">Loading booking history...</td>
                </tr>
              ) : null}
            </tbody>
          </table>
          {/* Pagination Controls */}
          {!bookingHistoryLoading && bookingHistory.length > HISTORY_PAGE_SIZE && (
            <Pagination
              page={historyPage}
              totalPages={Math.ceil(bookingHistory.length / HISTORY_PAGE_SIZE) || 1}
              onPageChange={setHistoryPage}
            />
          )}
        </div>
      </section>

      {imageModalMarkup}

    </form>
  );
}

function formatHistoryDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function formatCurrency(value) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "-";
  return `NPR ${amount.toLocaleString()}`;
}

function formatPaymentCell(booking) {
  const method = String(booking?.paymentMethod || "").trim();
  const status = String(booking?.paymentStatus || "").trim();
  if (method && status) return `${method} (${status})`;
  if (method) return method;
  if (status) return status;
  return "Not recorded";
}
