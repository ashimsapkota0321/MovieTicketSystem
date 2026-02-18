import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  AtSign,
  Building2,
  Calendar,
  Camera,
  Check,
  LogOut,
  Mail,
  MapPin,
  Pencil,
  Phone,
} from "lucide-react";
import "../css/profile.css";

const STORAGE_KEY = "vendor";
const UPDATE_EVENT = "mt:vendor-updated";
const API_BASE_URL = "http://localhost:8000/api";

const EMPTY_PROFILE = {
  name: "",
  email: "",
  phone_number: "",
  username: "",
  theatre: "",
  city: "",
  status: "",
  is_active: true,
  created_at: "",
  avatar: "",
};

const getStoredVendor = () => {
  if (typeof window === "undefined") return null;
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
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
  if (profile.name) return profile.name;
  if (profile.username) return profile.username;
  if (profile.email) return profile.email;
  if (profile.phone_number) return profile.phone_number;
  if (profile.phone) return profile.phone;
  return "";
};

const getInitials = (name) => {
  const trimmed = String(name || "").trim();
  if (!trimmed) return "VN";
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

const formatActive = (value) => {
  if (value === true) return "Active";
  if (value === false) return "Inactive";
  return "Not set";
};

const formatDate = (value) => {
  if (!value) return "Not set";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleDateString();
};

const revokePreviewUrl = (url) => {
  if (url && url.startsWith("blob:")) {
    URL.revokeObjectURL(url);
  }
};

const deriveProfile = (user) => ({
  ...EMPTY_PROFILE,
  name: user?.name || "",
  email: user?.email || "",
  phone_number: user?.phone_number || user?.phone || "",
  username: user?.username || getDefaultUsername(user),
  theatre: user?.theatre || "",
  city: user?.city || "",
  status: user?.status || "",
  is_active: user?.is_active ?? user?.isActive ?? true,
  created_at: user?.created_at || user?.createdAt || "",
  avatar:
    user?.avatar ||
    user?.avatarUrl ||
    user?.profile_image ||
    user?.profileImage ||
    user?.photo ||
    user?.image ||
    "",
});

export default function VendorProfile() {
  const navigate = useNavigate();
  const [vendor, setVendor] = useState(() => getStoredVendor());
  const [formData, setFormData] = useState(() =>
    deriveProfile(getStoredVendor())
  );
  const [statusMessage, setStatusMessage] = useState(null);
  const [isEditing, setIsEditing] = useState(false);
  const [avatarFile, setAvatarFile] = useState(null);
  const [removeAvatar, setRemoveAvatar] = useState(false);
  const [isImageOpen, setImageOpen] = useState(false);

  useEffect(() => {
    if (!vendor) {
      navigate("/login");
    }
  }, [vendor, navigate]);

  useEffect(() => {
    if (vendor) {
      setFormData(deriveProfile(vendor));
    }
  }, [vendor]);

  useEffect(() => {
    if (!statusMessage || statusMessage.type !== "success") return;
    const timer = setTimeout(() => setStatusMessage(null), 2000);
    return () => clearTimeout(timer);
  }, [statusMessage]);

  const handleChange = (event) => {
    const { name, value } = event.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

  const handleAvatarChange = (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setStatusMessage({ type: "error", message: "Please select an image file." });
      event.target.value = "";
      return;
    }
    revokePreviewUrl(formData.avatar);
    const previewUrl = URL.createObjectURL(file);
    setFormData((prev) => ({ ...prev, avatar: previewUrl }));
    setAvatarFile(file);
    setRemoveAvatar(false);
    setStatusMessage(null);
    setIsEditing(true);
    event.target.value = "";
  };

  const handleRemoveAvatar = () => {
    if (!formData.avatar) return;
    revokePreviewUrl(formData.avatar);
    setFormData((prev) => ({ ...prev, avatar: "" }));
    setAvatarFile(null);
    setRemoveAvatar(true);
    setStatusMessage(null);
    setIsEditing(true);
  };

  const handleEditToggle = () => {
    if (!isEditing) {
      setIsEditing(true);
      setStatusMessage(null);
    }
  };

  const handleCancel = () => {
    revokePreviewUrl(formData.avatar);
    setFormData(deriveProfile(vendor));
    setAvatarFile(null);
    setRemoveAvatar(false);
    setIsEditing(false);
    setStatusMessage(null);
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
    if (!vendor || !isEditing) return;

    if (!vendor?.id) {
      setStatusMessage({
        type: "error",
        message: "Vendor ID missing. Please log in again.",
      });
      return;
    }

    const normalizedName = String(formData.name ?? "").trim();
    const normalizedPhone = String(formData.phone_number ?? "").trim();
    const normalizedTheatre = String(formData.theatre ?? "").trim();
    const normalizedCity = String(formData.city ?? "").trim();

    if (!normalizedName) {
      setStatusMessage({
        type: "error",
        message: "Vendor name is required.",
      });
      return;
    }

    const currentName = String(vendor?.name || "").trim();
    const currentPhone = String(vendor?.phone_number || vendor?.phone || "").trim();
    const currentTheatre = String(vendor?.theatre || "").trim();
    const currentCity = String(vendor?.city || "").trim();

    const payload = {};
    if (normalizedName !== currentName) {
      payload.name = normalizedName;
    }
    if (normalizedPhone !== currentPhone) {
      payload.phone_number = normalizedPhone;
    }
    if (normalizedTheatre !== currentTheatre) {
      payload.theatre = normalizedTheatre;
    }
    if (normalizedCity !== currentCity) {
      payload.city = normalizedCity;
    }

    const hasAvatarChange = Boolean(avatarFile) || removeAvatar;

    if (!Object.keys(payload).length && !hasAvatarChange) {
      setStatusMessage({
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
        },
      };

      if (hasAvatarChange) {
        const formPayload = new FormData();
        Object.entries(payload).forEach(([key, value]) => {
          formPayload.append(key, value ?? "");
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
        `${API_BASE_URL}/profile/vendor/${vendor.id}/`,
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

      const updatedVendor = {
        ...vendor,
        ...(data && data.vendor ? data.vendor : {}),
      };

      revokePreviewUrl(formData.avatar);
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(updatedVendor));
      setVendor(updatedVendor);
      setFormData(deriveProfile(updatedVendor));
      setAvatarFile(null);
      setRemoveAvatar(false);
      setIsEditing(false);
      setStatusMessage({ type: "success", message: "Profile updated." });
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(UPDATE_EVENT));
      }
    } catch (err) {
      console.error("Vendor profile update error:", err);
      setStatusMessage({
        type: "error",
        message: err.message || "Failed to update profile.",
      });
    }
  };

  const handleLogout = () => {
    sessionStorage.removeItem(STORAGE_KEY);
    setVendor(null);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event(UPDATE_EVENT));
    }
    navigate("/login");
  };

  if (!vendor) return null;

  const displayName = getDisplayName(formData);
  const initials = getInitials(displayName);

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
                {displayName || "Vendor"}
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
                {formData.username || "vendor"}
              </span>
            </div>

            {statusMessage ? (
              <div
                className={`wf2-profileStatus ${
                  statusMessage.type === "success"
                    ? "wf2-profileStatusSuccess"
                    : "wf2-profileStatusError"
                }`}
              >
                {statusMessage.message}
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
                  <span>Vendor name</span>
                  <div className="wf2-profileInputRow">
                    <input
                      className="wf2-profileInput"
                      name="name"
                      type="text"
                      value={formData.name}
                      onChange={handleChange}
                      placeholder="Vendor name"
                    />
                  </div>
                </label>
                <label className="wf2-profileField">
                  <span>Phone number</span>
                  <div className="wf2-profileInputRow">
                    <Phone size={16} />
                    <input
                      className="wf2-profileInput"
                      name="phone_number"
                      type="tel"
                      value={formData.phone_number}
                      onChange={handleChange}
                      placeholder="Phone number"
                    />
                  </div>
                </label>
                <label className="wf2-profileField">
                  <span>Theatre</span>
                  <div className="wf2-profileInputRow">
                    <Building2 size={16} />
                    <input
                      className="wf2-profileInput"
                      name="theatre"
                      type="text"
                      value={formData.theatre}
                      onChange={handleChange}
                      placeholder="Theatre name"
                    />
                  </div>
                </label>
                <label className="wf2-profileField">
                  <span>City</span>
                  <div className="wf2-profileInputRow">
                    <MapPin size={16} />
                    <input
                      className="wf2-profileInput"
                      name="city"
                      type="text"
                      value={formData.city}
                      onChange={handleChange}
                      placeholder="City"
                    />
                  </div>
                </label>
                <label className="wf2-profileField">
                  <span>Username (locked)</span>
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
                  <span>Status (locked)</span>
                  <div className="wf2-profileInputRow wf2-profileInputRowLocked">
                    <Check size={16} />
                    <input
                      className="wf2-profileInput"
                      name="status"
                      type="text"
                      value={formatValue(formData.status)}
                      readOnly
                      disabled
                    />
                  </div>
                </label>
                <label className="wf2-profileField">
                  <span>Account active (locked)</span>
                  <div className="wf2-profileInputRow wf2-profileInputRowLocked">
                    <Check size={16} />
                    <input
                      className="wf2-profileInput"
                      name="is_active"
                      type="text"
                      value={formatActive(formData.is_active)}
                      readOnly
                      disabled
                    />
                  </div>
                </label>
                <label className="wf2-profileField">
                  <span>Created at (locked)</span>
                  <div className="wf2-profileInputRow wf2-profileInputRowLocked">
                    <Calendar size={16} />
                    <input
                      className="wf2-profileInput"
                      name="created_at"
                      type="text"
                      value={formatDate(formData.created_at)}
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
                <span>Vendor name</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.name)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Phone number</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.phone_number)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Theatre</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.theatre)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>City</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.city)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Username</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.username)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Email</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.email)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Status</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.status)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Account active</span>
                <div className="wf2-profileViewValue">
                  {formatActive(formData.is_active)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Created at</span>
                <div className="wf2-profileViewValue">
                  {formatDate(formData.created_at)}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      {isImageOpen && formData.avatar ? (
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
              x
            </button>
            <img
              className="wf2-profileImageFull"
              src={formData.avatar}
              alt="Profile full size"
            />
          </div>
        </div>
      ) : null}
    </form>
  );
}
