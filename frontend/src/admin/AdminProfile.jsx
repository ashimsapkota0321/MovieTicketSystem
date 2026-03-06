import React, { useEffect, useState } from "react";
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
import { clearAuthSession, getAuthHeaders } from "../lib/authSession";

const STORAGE_KEY = "admin";
const UPDATE_EVENT = "mt:admin-updated";
const API_BASE_URL = "http://localhost:8000/api";

const EMPTY_PROFILE = {
  full_name: "",
  email: "",
  phone_number: "",
  username: "",
  is_active: true,
  date_joined: "",
  avatar: "",
};

const getStoredAdmin = () => {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(STORAGE_KEY);
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
  if (profile.full_name) return profile.full_name;
  if (profile.name) return profile.name;
  if (profile.username) return profile.username;
  if (profile.email) return profile.email;
  if (profile.phone_number) return profile.phone_number;
  if (profile.phone) return profile.phone;
  return "";
};

const getInitials = (name) => {
  const trimmed = String(name || "").trim();
  if (!trimmed) return "AD";
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
  full_name: user?.full_name || user?.fullName || user?.name || "",
  email: user?.email || "",
  phone_number: user?.phone_number || user?.phone || "",
  username: user?.username || getDefaultUsername(user),
  is_active: user?.is_active ?? user?.isActive ?? true,
  date_joined: user?.date_joined || user?.dateJoined || user?.created_at || "",
  avatar:
    user?.avatar ||
    user?.avatarUrl ||
    user?.profile_image ||
    user?.profileImage ||
    user?.photo ||
    user?.image ||
    "",
});

export default function AdminProfile() {
  const navigate = useNavigate();
  const [admin, setAdmin] = useState(() => getStoredAdmin());
  const [formData, setFormData] = useState(() =>
    deriveProfile(getStoredAdmin())
  );
  const [status, setStatus] = useState(null);
  const [isEditing, setIsEditing] = useState(false);
  const [avatarFile, setAvatarFile] = useState(null);
  const [removeAvatar, setRemoveAvatar] = useState(false);
  const [isImageOpen, setImageOpen] = useState(false);

  useEffect(() => {
    if (!admin) {
      navigate("/login");
    }
  }, [admin, navigate]);

  useEffect(() => {
    if (admin) {
      setFormData(deriveProfile(admin));
    }
  }, [admin]);

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
    setFormData(deriveProfile(admin));
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
    if (!admin || !isEditing) return;

    if (!admin?.id) {
      setStatus({
        type: "error",
        message: "Admin ID missing. Please log in again.",
      });
      return;
    }

    const currentFullName = String(
      admin?.full_name || admin?.fullName || admin?.name || ""
    ).trim();
    const currentPhone = String(admin?.phone_number || admin?.phone || "").trim();
    const normalizedFullName = String(formData.full_name ?? "").trim();
    const normalizedPhone = String(formData.phone_number ?? "").trim();

    const payload = {};
    if (normalizedFullName !== currentFullName) {
      payload.full_name = normalizedFullName;
    }
    if (normalizedPhone !== currentPhone) {
      payload.phone_number = normalizedPhone;
    }

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
        `${API_BASE_URL}/profile/admin/${admin.id}/`,
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

      const updatedAdmin = {
        ...admin,
        ...(data && data.admin ? data.admin : {}),
      };

      revokePreviewUrl(formData.avatar);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedAdmin));
      setAdmin(updatedAdmin);
      setFormData(deriveProfile(updatedAdmin));
      setAvatarFile(null);
      setRemoveAvatar(false);
      setIsEditing(false);
      setStatus({ type: "success", message: "Profile updated." });
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(UPDATE_EVENT));
      }
    } catch (err) {
      console.error("Admin profile update error:", err);
      setStatus({
        type: "error",
        message: err.message || "Failed to update profile.",
      });
    }
  };

  const handleLogout = () => {
    clearAuthSession();
    localStorage.removeItem(STORAGE_KEY);
    setAdmin(null);
    if (typeof window !== "undefined") {
      window.dispatchEvent(new Event(UPDATE_EVENT));
    }
    navigate("/login");
  };

  if (!admin) return null;

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
                {displayName || "Admin"}
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
                {formData.username || "admin"}
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
                  <span>Full name</span>
                  <div className="wf2-profileInputRow">
                    <input
                      className="wf2-profileInput"
                      name="full_name"
                      type="text"
                      value={formData.full_name}
                      onChange={handleChange}
                      placeholder="Full name"
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
                      value={formatActive(formData.is_active)}
                      readOnly
                      disabled
                    />
                  </div>
                </label>
                <label className="wf2-profileField">
                  <span>Date joined (locked)</span>
                  <div className="wf2-profileInputRow wf2-profileInputRowLocked">
                    <Calendar size={16} />
                    <input
                      className="wf2-profileInput"
                      name="date_joined"
                      type="text"
                      value={formatDate(formData.date_joined)}
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
                <span>Full name</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.full_name)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Phone number</span>
                <div className="wf2-profileViewValue">
                  {formatValue(formData.phone_number)}
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
                  {formatActive(formData.is_active)}
                </div>
              </div>
              <div className="wf2-profileField">
                <span>Date joined</span>
                <div className="wf2-profileViewValue">
                  {formatDate(formData.date_joined)}
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
