import { createElement, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  Camera,
  CameraOff,
  CheckCircle2,
  Clock3,
  Download,
  ImageUp,
  Keyboard,
  RefreshCcw,
  Search,
  ShieldAlert,
  Ticket,
} from "lucide-react";
import jsQR from "jsqr";
import {
  exportVendorTicketValidationMonitorCsv,
  fetchVendorTicketValidationMonitor,
  validateVendorTicket,
} from "../lib/catalogApi";

const SCAN_FRAME_INTERVAL_MS = 220;
const VIDEO_READY_TIMEOUT_MS = 6000;
const VIDEO_ELEMENT_WAIT_TIMEOUT_MS = 2500;
const MAX_UPLOAD_IMAGE_SIDE = 1800;
const REFERENCE_PATTERN = /^[A-Z0-9][A-Z0-9_-]{3,19}$/;
const TICKET_PATH_PATTERN = /\/ticket\/([^/?#]+)\//i;
const SCANNER_MODES = [
  { id: "camera", label: "Camera", icon: Camera },
  { id: "manual", label: "Manual Entry", icon: Keyboard },
  { id: "upload", label: "Image Upload", icon: ImageUp },
];
const EMPTY_MONITOR_FILTERS = {
  date: "",
  staff: "",
  status: "",
  movie: "",
  show: "",
  reference: "",
};
const FALLBACK_MONITOR_STATUS_OPTIONS = [
  { value: "VALID", label: "VALID" },
  { value: "DUPLICATE", label: "DUPLICATE" },
  { value: "INVALID", label: "INVALID" },
  { value: "FRAUD", label: "FRAUD" },
];
const MONITOR_ALERT_TITLES = {
  duplicate_ticket: "Duplicate Ticket Alerts",
  fraud_suspected: "Fraud/Invalid Alerts",
  invalid_token_spike: "Invalid Token Spike",
  repeated_duplicate_attempts: "Repeated Duplicate Attempts",
};
const SCAN_STATUS_TO_CODE = {
  VALID: "SCAN_VALID",
  DUPLICATE: "SCAN_ALREADY_USED",
  INVALID: "SCAN_INVALID_TOKEN",
  FRAUD: "SCAN_WRONG_VENDOR",
};
const SCAN_UX_OUTCOMES = {
  SCAN_VALID: {
    tone: "success",
    state: "success",
    stateLabel: "SUCCESS",
    title: "Entry Approved",
    hint: "Ticket is valid. Admit customer and continue to the next scan.",
    retryMessage: "No retry required.",
    recommendRetry: false,
  },
  SCAN_ALREADY_USED: {
    tone: "warning",
    state: "warning",
    stateLabel: "WARNING",
    title: "Duplicate Ticket",
    hint: "This ticket was already used.",
    retryMessage: "Retry once only if the previous scan was interrupted.",
    recommendRetry: true,
  },
  SCAN_TICKET_NOT_FOUND: {
    tone: "warning",
    state: "retry",
    stateLabel: "RETRY",
    title: "Ticket Not Found",
    hint: "The scanned value does not match a valid ticket.",
    retryMessage: "Ask customer to reopen QR and retry. Use fallback mode if needed.",
    recommendRetry: true,
  },
  SCAN_LOOKUP_INVALID: {
    tone: "warning",
    state: "retry",
    stateLabel: "RETRY",
    title: "Invalid Scan Input",
    hint: "Scanner input format is incomplete.",
    retryMessage: "Retry with full ticket reference, ticket id, URL, or QR payload.",
    recommendRetry: true,
  },
  SCAN_INVALID_TOKEN: {
    tone: "warning",
    state: "retry",
    stateLabel: "RETRY",
    title: "Invalid QR Token",
    hint: "QR token is missing or malformed.",
    retryMessage: "Scan the original QR again (avoid cropped screenshots).",
    recommendRetry: true,
  },
  SCAN_EXPIRED_TOKEN: {
    tone: "warning",
    state: "retry",
    stateLabel: "RETRY",
    title: "QR Token Expired",
    hint: "This QR token is no longer valid.",
    retryMessage: "Ask customer to regenerate ticket QR and retry.",
    recommendRetry: true,
  },
  SCAN_OUTSIDE_VALID_TIME_WINDOW: {
    tone: "warning",
    state: "warning",
    stateLabel: "WARNING",
    title: "Outside Valid Entry Window",
    hint: "Ticket is too early or already expired for this show.",
    retryMessage: "Retry only during the valid check-in window.",
    recommendRetry: false,
  },
  SCAN_PAYMENT_INCOMPLETE: {
    tone: "warning",
    state: "warning",
    stateLabel: "WARNING",
    title: "Payment Incomplete",
    hint: "Payment is not confirmed for this ticket.",
    retryMessage: "Retry after payment is completed.",
    recommendRetry: false,
  },
  SCAN_WRONG_VENDOR: {
    tone: "danger",
    state: "danger",
    stateLabel: "ALERT",
    title: "Vendor Mismatch Fraud Alert",
    hint: "Ticket belongs to another vendor/cinema.",
    retryMessage: "Do not admit customer. Escalate to supervisor.",
    recommendRetry: false,
  },
  SCAN_RATE_LIMITED: {
    tone: "warning",
    state: "retry",
    stateLabel: "RETRY",
    title: "Rate Limit Active",
    hint: "Too many scan requests were submitted in a short period.",
    retryMessage: (retryAfterSeconds) =>
      retryAfterSeconds > 0
        ? `Wait ${retryAfterSeconds}s, then retry scan.`
        : "Wait a moment, then retry scan.",
    recommendRetry: true,
  },
};

function resolveScanUxState(outcome = {}) {
  const normalizedCode = String(outcome?.code || "").trim().toUpperCase();
  const normalizedStatus = String(outcome?.status || "").trim().toUpperCase();
  const mappedCode = normalizedCode || SCAN_STATUS_TO_CODE[normalizedStatus] || "";
  const rawRetryAfter = Number(outcome?.retryAfterSeconds || 0);
  const retryAfterSeconds = Number.isFinite(rawRetryAfter)
    ? Math.max(0, Math.floor(rawRetryAfter))
    : 0;

  const preset = SCAN_UX_OUTCOMES[mappedCode];
  if (preset) {
    const retryMessage =
      typeof preset.retryMessage === "function"
        ? preset.retryMessage(retryAfterSeconds)
        : preset.retryMessage;
    return {
      code: mappedCode,
      tone: preset.tone,
      state: preset.state,
      stateLabel: preset.stateLabel,
      title: preset.title,
      hint: preset.hint,
      retryMessage,
      recommendRetry: Boolean(preset.recommendRetry),
    };
  }

  if (outcome?.isError) {
    return {
      code: mappedCode,
      tone: "danger",
      state: "retry",
      stateLabel: "RETRY",
      title: "Scan Failed",
      hint: "Validation did not complete.",
      retryMessage: "Retry scan or switch to manual/image fallback mode.",
      recommendRetry: true,
    };
  }

  return {
    code: mappedCode,
    tone: "warning",
    state: "warning",
    stateLabel: "WARNING",
    title: "Validation Warning",
    hint: "Review the scan details before allowing entry.",
    retryMessage: "Retry only after confirming the ticket details.",
    recommendRetry: false,
  };
}

function toPositiveInt(value) {
  if (value === null || value === undefined) return null;
  const parsed = Number.parseInt(String(value).trim(), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function normalizeReference(value) {
  const reference = String(value || "").trim().toUpperCase();
  if (!reference || reference.length > 20) return "";
  if (!REFERENCE_PATTERN.test(reference)) return "";
  return reference;
}

function parseScanUrl(value) {
  try {
    const url = new URL(value);
    const pathMatch = url.pathname.match(TICKET_PATH_PATTERN);
    if (pathMatch) {
      const reference = normalizeReference(pathMatch[1]);
      if (reference) {
        return { reference, ticketId: null };
      }
    }

    for (const key of ["reference", "ticket_reference", "ticketRef", "ticket_ref"]) {
      const reference = normalizeReference(url.searchParams.get(key));
      if (reference) {
        return { reference, ticketId: null };
      }
    }

    for (const key of ["ticket_id", "ticketId", "id"]) {
      const ticketId = toPositiveInt(url.searchParams.get(key));
      if (ticketId) {
        return { reference: "", ticketId };
      }
    }
  } catch {
    // Ignore invalid URL values.
  }
  return { reference: "", ticketId: null };
}

function buildTicketScanPayload(value) {
  const raw = String(value || "").trim();
  if (!raw) return {};

  const directReference = normalizeReference(raw);
  if (directReference) {
    return { reference: directReference };
  }

  if (/^\d+$/.test(raw)) {
    const ticketId = toPositiveInt(raw);
    if (ticketId) {
      return { ticket_id: ticketId };
    }
  }

  let reference = "";
  let ticketId = null;

  const fromUrl = parseScanUrl(raw);
  reference = fromUrl.reference;
  ticketId = fromUrl.ticketId;

  if (!reference && !ticketId) {
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        for (const key of ["reference", "ticket_reference", "ticketRef", "ticket_ref"]) {
          reference = normalizeReference(parsed[key]);
          if (reference) break;
        }
        if (!reference) {
          for (const key of ["ticket_id", "ticketId", "id"]) {
            ticketId = toPositiveInt(parsed[key]);
            if (ticketId) break;
          }
        }
        if (!reference && !ticketId) {
          const detailsUrl = String(parsed.details_url || parsed.url || "").trim();
          if (detailsUrl) {
            const fromDetails = parseScanUrl(detailsUrl);
            reference = fromDetails.reference;
            ticketId = fromDetails.ticketId;
          }
        }
      }
    } catch {
      // Ignore non-JSON values.
    }
  }

  if (!reference && !ticketId) {
    const pathMatch = raw.match(TICKET_PATH_PATTERN);
    if (pathMatch) {
      reference = normalizeReference(pathMatch[1]);
    }
  }

  if (!reference && !ticketId) {
    const queryReference = raw.match(/(?:reference|ticket_reference|ticketRef|ticket_ref)=([A-Za-z0-9_-]{4,30})/i);
    if (queryReference) {
      reference = normalizeReference(queryReference[1]);
    }
  }

  if (!ticketId) {
    const queryTicketId = raw.match(/(?:ticket_id|ticketId|id)=(\d{1,12})/i);
    if (queryTicketId) {
      ticketId = toPositiveInt(queryTicketId[1]);
    }
  }

  const payload = { scan_data: raw };
  if (reference) payload.reference = reference;
  if (ticketId) payload.ticket_id = ticketId;
  return payload;
}

function extractRetryValue(payload, rawValue) {
  if (rawValue) return String(rawValue).trim();
  if (!payload || typeof payload !== "object") return "";
  if (payload.scan_data) return String(payload.scan_data).trim();
  if (payload.reference) return String(payload.reference).trim();
  if (payload.ticket_id) return String(payload.ticket_id).trim();
  return "";
}

function toWholeNumber(value, fallback = 0) {
  const parsed = Number.parseInt(String(value ?? "").trim(), 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function buildMonitorAlertDisplay(alert) {
  const type = String(alert?.type || "").trim();
  const normalizedType = type || "unknown";
  const count = toWholeNumber(alert?.count, 0);
  const severityRaw = String(alert?.severity || "").trim().toLowerCase();
  const isTriggered =
    typeof alert?.isTriggered === "boolean" ? alert.isTriggered : count > 0;
  const severity = ["danger", "warning", "info"].includes(severityRaw)
    ? severityRaw
    : isTriggered
      ? "warning"
      : "info";

  const title = String(
    alert?.title || MONITOR_ALERT_TITLES[normalizedType] || "Validation Alert"
  ).trim();
  const message = String(alert?.message || "").trim();
  const windowMinutes = toWholeNumber(alert?.windowMinutes, 0);
  const previousWindowCount = toWholeNumber(alert?.previousWindowCount, 0);
  const threshold = toWholeNumber(alert?.threshold, 0);
  const repeatedTicketCount = toWholeNumber(alert?.repeatedTicketCount, 0);
  const totalInWindow = toWholeNumber(alert?.totalInWindow, count);

  let details = "";
  if (normalizedType === "invalid_token_spike") {
    const detailParts = [];
    if (windowMinutes > 0) detailParts.push(`Window: last ${windowMinutes} min`);
    detailParts.push(`Current: ${count}`);
    detailParts.push(`Previous: ${previousWindowCount}`);
    if (threshold > 0) detailParts.push(`Threshold: ${threshold}`);
    details = detailParts.join(" | ");
  } else if (normalizedType === "repeated_duplicate_attempts") {
    const detailParts = [];
    if (windowMinutes > 0) detailParts.push(`Window: last ${windowMinutes} min`);
    detailParts.push(`Duplicates: ${totalInWindow}`);
    if (repeatedTicketCount > 0) detailParts.push(`Tickets flagged: ${repeatedTicketCount}`);
    if (threshold > 0) detailParts.push(`Threshold: ${threshold}`);
    details = detailParts.join(" | ");
  }

  const offenders = Array.isArray(alert?.offenders)
    ? alert.offenders
        .map((item) => ({
          reference: String(item?.reference || "").trim() || "UNKNOWN",
          ticketId: item?.ticketId ? String(item.ticketId).trim() : "",
          duplicateAttempts: toWholeNumber(item?.duplicateAttempts, 0),
        }))
        .filter((item) => item.reference || item.ticketId || item.duplicateAttempts > 0)
        .slice(0, 4)
    : [];

  return {
    type: normalizedType,
    title,
    message,
    count,
    details,
    severity,
    isTriggered,
    offenders,
  };
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Unable to read uploaded image."));
    reader.readAsDataURL(file);
  });
}

function loadImageElement(src) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Uploaded image could not be processed."));
    image.src = src;
  });
}

async function decodeQrFromImageFile(file) {
  if (!file || !String(file.type || "").startsWith("image/")) {
    throw new Error("Please upload a valid image file containing a QR code.");
  }

  const dataUrl = await readFileAsDataUrl(file);
  const image = await loadImageElement(dataUrl);

  const sourceWidth = Math.max(1, image.naturalWidth || image.width || 1);
  const sourceHeight = Math.max(1, image.naturalHeight || image.height || 1);
  const scale = Math.min(1, MAX_UPLOAD_IMAGE_SIDE / Math.max(sourceWidth, sourceHeight));

  const width = Math.max(1, Math.floor(sourceWidth * scale));
  const height = Math.max(1, Math.floor(sourceHeight * scale));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;

  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) {
    throw new Error("Unable to decode QR from image in this browser.");
  }

  context.drawImage(image, 0, 0, width, height);

  const runDecode = (sx, sy, sw, sh) => {
    const imageData = context.getImageData(sx, sy, sw, sh);
    const decoded = jsQR(imageData.data, sw, sh, {
      inversionAttempts: "attemptBoth",
    });
    return String(decoded?.data || "").trim();
  };

  let decodedValue = runDecode(0, 0, width, height);
  if (decodedValue) return decodedValue;

  const cropSize = Math.floor(Math.min(width, height) * 0.75);
  if (cropSize >= 120) {
    const cropX = Math.floor((width - cropSize) / 2);
    const cropY = Math.floor((height - cropSize) / 2);
    decodedValue = runDecode(cropX, cropY, cropSize, cropSize);
    if (decodedValue) return decodedValue;
  }

  throw new Error("No readable QR code found. Try a clearer image or use manual entry.");
}

export default function VendorTicketValidation() {
  const [reference, setReference] = useState("");
  const [scannerMode, setScannerMode] = useState("camera");
  const [isScanning, setIsScanning] = useState(false);
  const [isStartingCamera, setIsStartingCamera] = useState(false);
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [availableCameras, setAvailableCameras] = useState([]);
  const [activeDeviceId, setActiveDeviceId] = useState("");
  const [isDecodingUpload, setIsDecodingUpload] = useState(false);
  const [cameraError, setCameraError] = useState("");
  const [lastScanValue, setLastScanValue] = useState("");
  const [scanResult, setScanResult] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState("success");
  const [scanOutcome, setScanOutcome] = useState(null);
  const [monitorError, setMonitorError] = useState("");
  const [monitorNotice, setMonitorNotice] = useState("");
  const [monitorData, setMonitorData] = useState({
    summary: {},
    realtime: {
      todayScans: 0,
      todayFailedScans: 0,
      todayValidScans: 0,
      todayDuplicateScans: 0,
      todayFailedRate: 0,
      hourlyScanTrend: [],
      updatedAt: null,
    },
    alerts: [],
    scans: [],
    filters: { staff: [], movies: [], shows: [], statuses: [] },
  });
  const [monitorFilters, setMonitorFilters] = useState(EMPTY_MONITOR_FILTERS);
  const [isLoading, setIsLoading] = useState(false);
  const [isExportingCsv, setIsExportingCsv] = useState(false);
  const [search, setSearch] = useState("");

  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const decodeIntervalRef = useRef(null);
  const videoReadyTimeoutRef = useRef(null);
  const decodeBusyRef = useRef(false);
  const uploadInputRef = useRef(null);
  const lastDecodedValueRef = useRef("");

  const clearVideoReadyTimeout = useCallback(() => {
    if (videoReadyTimeoutRef.current) {
      window.clearTimeout(videoReadyTimeoutRef.current);
      videoReadyTimeoutRef.current = null;
    }
  }, []);

  const waitForVideoElement = useCallback((timeoutMs = VIDEO_ELEMENT_WAIT_TIMEOUT_MS) => {
    return new Promise((resolve, reject) => {
      const startedAt = Date.now();

      const tick = () => {
        if (videoRef.current) {
          resolve(videoRef.current);
          return;
        }

        if (Date.now() - startedAt >= timeoutMs) {
          reject(new Error("Camera preview element did not mount in time."));
          return;
        }

        if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
          window.requestAnimationFrame(tick);
        } else {
          window.setTimeout(tick, 16);
        }
      };

      tick();
    });
  }, []);

  const stopCameraScanner = useCallback(() => {
    clearVideoReadyTimeout();

    if (decodeIntervalRef.current) {
      window.clearInterval(decodeIntervalRef.current);
      decodeIntervalRef.current = null;
    }

    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    decodeBusyRef.current = false;
    setIsCameraOpen(false);
    setIsStartingCamera(false);
  }, [clearVideoReadyTimeout]);

  useEffect(() => {
    return () => {
      stopCameraScanner();
    };
  }, [stopCameraScanner]);

  const refreshCameraDevices = useCallback(async () => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.enumerateDevices) {
      return;
    }

    try {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const cameras = devices
        .filter((device) => device.kind === "videoinput")
        .map((device, index) => ({
          deviceId: device.deviceId,
          label: device.label || `Camera ${index + 1}`,
        }));

      setAvailableCameras(cameras);

      if (!activeDeviceId && cameras.length > 0) {
        setActiveDeviceId(cameras[0].deviceId);
      } else if (
        activeDeviceId &&
        cameras.length > 0 &&
        !cameras.some((camera) => camera.deviceId === activeDeviceId)
      ) {
        setActiveDeviceId(cameras[0].deviceId);
      }
    } catch {
      // Ignore camera device enumeration failures.
    }
  }, [activeDeviceId]);

  useEffect(() => {
    refreshCameraDevices();
  }, [refreshCameraDevices]);

  useEffect(() => {
    if (scannerMode !== "camera") {
      stopCameraScanner();
    }
  }, [scannerMode, stopCameraScanner]);

  const buildMonitorParams = useCallback(
    (overrides = {}, { includeLimit = true } = {}) => {
      const nextFilters = { ...monitorFilters, ...overrides };
      const params = {};
      if (includeLimit) {
        params.limit = 100;
      }

      const dateValue = String(nextFilters.date || "").trim();
      if (dateValue) params.date = dateValue;

      const staffValue = String(nextFilters.staff || "").trim();
      if (staffValue) params.staff = staffValue;

      const statusValue = String(nextFilters.status || "").trim().toUpperCase();
      if (statusValue) params.status = statusValue;

      const movieValue = String(nextFilters.movie || "").trim();
      if (movieValue) params.movie = movieValue;

      const showValue = String(nextFilters.show || "").trim();
      if (showValue) params.show = showValue;

      const referenceValue = String(nextFilters.reference || "").trim().toUpperCase();
      if (referenceValue) params.reference = referenceValue;

      return params;
    },
    [monitorFilters]
  );

  const loadMonitor = useCallback(async (params = {}) => {
    setIsLoading(true);
    setMonitorError("");
    try {
      const data = await fetchVendorTicketValidationMonitor(params);
      setMonitorData({
        summary: data?.summary || {},
        realtime: data?.realtime || {
          todayScans: 0,
          todayFailedScans: 0,
          todayValidScans: 0,
          todayDuplicateScans: 0,
          todayFailedRate: 0,
          hourlyScanTrend: [],
          updatedAt: null,
        },
        alerts: Array.isArray(data?.alerts) ? data.alerts : [],
        scans: Array.isArray(data?.scans) ? data.scans : [],
        filters: {
          staff: Array.isArray(data?.filters?.staff) ? data.filters.staff : [],
          movies: Array.isArray(data?.filters?.movies) ? data.filters.movies : [],
          shows: Array.isArray(data?.filters?.shows) ? data.filters.shows : [],
          statuses: Array.isArray(data?.filters?.statuses) ? data.filters.statuses : [],
        },
      });
    } catch (err) {
      setMonitorError(err.message || "Unable to load validation logs.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMonitor({ limit: 100 });
  }, [loadMonitor]);

  useEffect(() => {
    const refreshTimer = window.setInterval(() => {
      loadMonitor(buildMonitorParams());
    }, 20000);

    return () => {
      window.clearInterval(refreshTimer);
    };
  }, [buildMonitorParams, loadMonitor]);

  const updateMonitorFilter = useCallback((field, value) => {
    setMonitorFilters((prev) => ({ ...prev, [field]: value }));
  }, []);

  const applyMonitorFilters = useCallback(async () => {
    setMonitorError("");
    setMonitorNotice("");
    await loadMonitor(buildMonitorParams());
  }, [buildMonitorParams, loadMonitor]);

  const resetMonitorFilters = useCallback(async () => {
    setMonitorFilters(EMPTY_MONITOR_FILTERS);
    setMonitorError("");
    setMonitorNotice("");
    await loadMonitor({ limit: 100 });
  }, [loadMonitor]);

  const handleExportMonitorCsv = useCallback(async () => {
    if (isExportingCsv) return;

    setMonitorError("");
    setMonitorNotice("");
    setIsExportingCsv(true);
    try {
      const { blob, filename } = await exportVendorTicketValidationMonitorCsv(
        buildMonitorParams({}, { includeLimit: false })
      );

      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename || "ticket_validation_monitor.csv";
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(objectUrl);

      setMonitorNotice("Monitor CSV export is ready.");
    } catch (err) {
      setMonitorError(err.message || "Failed to export monitor CSV.");
    } finally {
      setIsExportingCsv(false);
    }
  }, [buildMonitorParams, isExportingCsv]);

  const filteredScans = useMemo(() => {
    const keyword = String(search || "").trim().toLowerCase();
    const scans = Array.isArray(monitorData.scans) ? monitorData.scans : [];
    if (!keyword) return scans;

    return scans.filter((scan) => {
      const value = [
        scan?.reference,
        scan?.status,
        scan?.reason,
        scan?.scannedByName,
        scan?.movieTitle,
        scan?.showLabel,
      ]
        .map((part) => String(part || "").toLowerCase())
        .join(" ");
      return value.includes(keyword);
    });
  }, [monitorData.scans, search]);

  const submitScan = useCallback(
    async (payload, { rawValue = "" } = {}) => {
      if (!payload?.reference && !payload?.ticket_id && !payload?.scan_data) {
        setError("Enter ticket reference, ticket id, or QR payload.");
        setScanOutcome({
          code: "SCAN_LOOKUP_INVALID",
          status: "",
          retryAfterSeconds: 0,
          isError: true,
        });
        return;
      }

      setError("");
      setNotice("");
      setCameraError("");
      setScanResult(null);
      setScanOutcome(null);
      setIsScanning(true);

      try {
        const result = await validateVendorTicket(payload);
        const nextScan = result?.scan || null;
        setScanResult(nextScan);

        if (nextScan?.reference) {
          setReference(nextScan.reference);
        }

        const retryValue = extractRetryValue(payload, rawValue);
        if (retryValue) {
          setLastScanValue(retryValue);
        }

        const scanStatus = String(nextScan?.status || "").toUpperCase();
        const outcomeCode = String(result?.code || "").trim().toUpperCase();
        const outcomeState = resolveScanUxState({
          code: outcomeCode,
          status: scanStatus,
          retryAfterSeconds: result?.retryAfterSeconds,
        });
        setScanOutcome({
          code: outcomeCode || outcomeState.code,
          status: scanStatus,
          retryAfterSeconds: Number(result?.retryAfterSeconds || 0),
          isError: false,
        });

        const nextTone = outcomeState.tone === "danger"
          ? "danger"
          : outcomeState.tone === "warning"
            ? "warning"
            : "success";
        setNoticeTone(nextTone);
        setNotice(result?.message || outcomeState.title);

        await loadMonitor(buildMonitorParams());
      } catch (err) {
        const errorScan = err?.scan && typeof err.scan === "object" ? err.scan : null;
        if (errorScan) {
          setScanResult(errorScan);
        }

        const errorStatus = String(errorScan?.status || "").trim().toUpperCase();
        const errorCode = String(err?.code || "").trim().toUpperCase();
        const outcomeState = resolveScanUxState({
          code: errorCode,
          status: errorStatus,
          retryAfterSeconds: err?.retryAfterSeconds,
          isError: true,
        });
        setScanOutcome({
          code: errorCode || outcomeState.code,
          status: errorStatus,
          retryAfterSeconds: Number(err?.retryAfterSeconds || 0),
          isError: true,
        });

        setNotice("");
        setNoticeTone(outcomeState.tone === "danger" ? "danger" : "warning");
        setError(err.message || "Scan failed. Retry or use manual/upload fallback.");
      } finally {
        setIsScanning(false);
      }
    },
    [buildMonitorParams, loadMonitor]
  );

  const handleManualScan = async () => {
    const rawValue = String(reference || "").trim();
    const payload = buildTicketScanPayload(rawValue);
    await submitScan(payload, { rawValue });
  };

  const startCameraScanner = async ({ deviceId } = {}) => {
    if (isCameraOpen || isStartingCamera) return;

    if (typeof window !== "undefined" && !window.isSecureContext) {
      setCameraError("Camera access requires HTTPS or localhost.");
      return;
    }

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setCameraError("Camera scanning is not supported in this browser.");
      return;
    }

    setCameraError("");
    setError("");
    setNotice("");
    setIsStartingCamera(true);

    try {
      const selectedDeviceId = String(deviceId || activeDeviceId || "").trim();
      const tryConstraintsList = selectedDeviceId
        ? [
            {
              audio: false,
              video: {
                deviceId: { exact: selectedDeviceId },
                width: { ideal: 1280 },
                height: { ideal: 720 },
              },
            },
            {
              audio: false,
              video: { deviceId: { exact: selectedDeviceId } },
            },
            {
              audio: false,
              video: {
                facingMode: { ideal: "environment" },
                width: { ideal: 1280 },
                height: { ideal: 720 },
              },
            },
            {
              audio: false,
              video: {
                facingMode: { ideal: "user" },
                width: { ideal: 1280 },
                height: { ideal: 720 },
              },
            },
            {
              audio: false,
              video: true,
            },
          ]
        : [
            {
              audio: false,
              video: {
                facingMode: { ideal: "environment" },
                width: { ideal: 1280 },
                height: { ideal: 720 },
              },
            },
            {
              audio: false,
              video: {
                facingMode: { ideal: "user" },
                width: { ideal: 1280 },
                height: { ideal: 720 },
              },
            },
            {
              audio: false,
              video: true,
            },
          ];

      let stream = null;
      let lastStreamError = null;
      for (const constraints of tryConstraintsList) {
        try {
          stream = await navigator.mediaDevices.getUserMedia(constraints);
          if (stream) break;
        } catch (streamError) {
          lastStreamError = streamError;
        }
      }

      if (!stream) {
        throw lastStreamError || new Error("Unable to open camera.");
      }

      mediaStreamRef.current = stream;
      setIsCameraOpen(true);
      lastDecodedValueRef.current = "";

      const [track] = stream.getVideoTracks();
      const trackSettings = track?.getSettings?.() || {};
      if (trackSettings.deviceId) {
        setActiveDeviceId(String(trackSettings.deviceId));
      }

      await refreshCameraDevices();

      const video = await waitForVideoElement();
      video.srcObject = stream;
      video.setAttribute("playsinline", "true");
      video.setAttribute("autoplay", "true");
      await video.play();

      clearVideoReadyTimeout();
      videoReadyTimeoutRef.current = window.setTimeout(() => {
        const activeVideo = videoRef.current;
        if (!activeVideo) return;
        const hasSignal =
          activeVideo.readyState >= 2 &&
          activeVideo.videoWidth > 0 &&
          activeVideo.videoHeight > 0;
        if (!hasSignal) {
          setCameraError("Camera opened but no live preview is available. Close other apps using camera (Zoom/Teams), then try again.");
          stopCameraScanner();
        }
      }, VIDEO_READY_TIMEOUT_MS);

      decodeIntervalRef.current = window.setInterval(() => {
        if (decodeBusyRef.current) return;

        const activeVideo = videoRef.current;
        if (!activeVideo || activeVideo.readyState < 2) return;

        clearVideoReadyTimeout();

        const width = activeVideo.videoWidth || 0;
        const height = activeVideo.videoHeight || 0;
        if (!width || !height) return;

        if (!canvasRef.current) {
          canvasRef.current = document.createElement("canvas");
        }
        const canvas = canvasRef.current;
        if (canvas.width !== width || canvas.height !== height) {
          canvas.width = width;
          canvas.height = height;
        }

        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) return;

        context.drawImage(activeVideo, 0, 0, width, height);
        const imageData = context.getImageData(0, 0, width, height);
        const decoded = jsQR(imageData.data, width, height, {
          inversionAttempts: "attemptBoth",
        });

        if (!decoded?.data) return;

        const rawValue = String(decoded.data).trim();
        if (!rawValue || rawValue === lastDecodedValueRef.current) return;

        decodeBusyRef.current = true;
        lastDecodedValueRef.current = rawValue;
        stopCameraScanner();

        const payload = buildTicketScanPayload(rawValue);
        submitScan(payload, { rawValue }).finally(() => {
          decodeBusyRef.current = false;
        });
      }, SCAN_FRAME_INTERVAL_MS);
    } catch (err) {
      const rawMessage = String(err?.message || "").trim();
      const normalized = rawMessage.toLowerCase();
      if (normalized.includes("denied") || normalized.includes("permission")) {
        setCameraError("Camera permission is blocked. Please allow camera access and try again.");
      } else if (normalized.includes("notfound") || normalized.includes("no camera")) {
        setCameraError("No camera device found on this system.");
      } else if (normalized.includes("notreadable") || normalized.includes("track start")) {
        setCameraError("Camera is busy in another application. Close other camera apps and retry.");
      } else if (normalized.includes("did not mount")) {
        setCameraError("Camera UI did not initialize correctly. Please refresh the page and try again.");
      } else {
        setCameraError(rawMessage || "Unable to start camera scanner.");
      }
      stopCameraScanner();
    } finally {
      setIsStartingCamera(false);
    }
  };

  const handleSwitchCamera = async () => {
    if (isStartingCamera || isScanning || isDecodingUpload) return;

    if (!availableCameras.length) {
      setCameraError("No alternate camera detected on this device.");
      return;
    }

    const currentIndex = availableCameras.findIndex(
      (camera) => camera.deviceId === activeDeviceId
    );
    const nextIndex = currentIndex >= 0
      ? (currentIndex + 1) % availableCameras.length
      : 0;
    const nextCamera = availableCameras[nextIndex];
    if (!nextCamera?.deviceId) {
      setCameraError("Unable to switch camera.");
      return;
    }

    setActiveDeviceId(nextCamera.deviceId);
    setCameraError("");
    setError("");
    setScanOutcome(null);
    setNoticeTone("success");
    setNotice(`Switched to ${nextCamera.label}.`);

    if (isCameraOpen) {
      stopCameraScanner();
      await startCameraScanner({ deviceId: nextCamera.deviceId });
    }
  };

  const retryLastScan = async () => {
    const retryValue = String(lastScanValue || "").trim();
    if (!retryValue || isScanning || isDecodingUpload) return;
    const payload = buildTicketScanPayload(retryValue);
    await submitScan(payload, { rawValue: retryValue });
  };

  const handleUploadSelection = async (event) => {
    const file = event?.target?.files?.[0];
    if (!file || isScanning) return;

    setError("");
    setNotice("");
    setCameraError("");
    setScanOutcome(null);
    setIsDecodingUpload(true);

    try {
      const decodedValue = await decodeQrFromImageFile(file);
      setReference(decodedValue);
      const payload = buildTicketScanPayload(decodedValue);
      await submitScan(payload, { rawValue: decodedValue });
    } catch (err) {
      setNotice("");
      setNoticeTone("warning");
      setError(err.message || "Unable to decode uploaded QR image.");
      setScanOutcome({
        code: "",
        status: "",
        retryAfterSeconds: 0,
        isError: true,
      });
    } finally {
      setIsDecodingUpload(false);
      if (event?.target) {
        event.target.value = "";
      }
    }
  };

  const activeCameraLabel = useMemo(() => {
    const matched = availableCameras.find((camera) => camera.deviceId === activeDeviceId);
    return matched?.label || "";
  }, [availableCameras, activeDeviceId]);

  const scanFeedback = useMemo(() => {
    if (isScanning) {
      return {
        tone: "info",
        title: "Validating Ticket",
        message: "Applying secure QR checks and duplicate-scan validation.",
        hint: "Please wait for the final decision.",
      };
    }

    if (isDecodingUpload) {
      return {
        tone: "info",
        title: "Decoding Uploaded Image",
        message: "Extracting QR payload from uploaded image...",
        hint: "This can take a moment for large files.",
      };
    }

    if (cameraError) {
      return {
        tone: "warning",
        state: "warning",
        stateLabel: "WARNING",
        code: "",
        title: "Camera Issue",
        message: cameraError,
        hint: "Use Manual Entry or Image Upload fallback mode.",
        retryMessage: "Retry camera after closing other apps using camera.",
        recommendRetry: true,
      };
    }

    if (scanOutcome) {
      const outcomeState = resolveScanUxState(scanOutcome);
      const outcomeMessage = scanOutcome.isError
        ? error || outcomeState.title
        : notice || outcomeState.title;
      return {
        ...outcomeState,
        message: outcomeMessage,
      };
    }

    if (error) {
      return {
        tone: "danger",
        state: "retry",
        stateLabel: "RETRY",
        code: "",
        title: "Scan Failed",
        message: error,
        hint: "Retry scan, switch camera, or use fallback modes.",
        retryMessage: "Use Retry Last Scan for immediate re-validation.",
        recommendRetry: true,
      };
    }

    if (notice) {
      const tone = noticeTone === "danger"
        ? "danger"
        : noticeTone === "warning"
          ? "warning"
          : "success";
      const state = tone === "success" ? "success" : tone === "warning" ? "warning" : "info";
      const stateLabel = tone === "success" ? "SUCCESS" : tone === "warning" ? "WARNING" : "INFO";

      return {
        tone,
        state,
        stateLabel,
        code: "",
        title: "Scanner Update",
        message: notice,
        hint: "Scanner mode or camera source has been updated.",
        retryMessage: "Resume scanning when ready.",
        recommendRetry: false,
      };
    }

    if (scannerMode === "camera") {
      return {
        tone: "muted",
        state: "ready",
        stateLabel: "READY",
        code: "",
        title: "Camera Mode Ready",
        message: "Start camera and align QR inside frame for automatic scan.",
        hint: "Use Switch Camera if rear/front feed is incorrect.",
        retryMessage: "For unstable scans, use Retry Last Scan after first decode.",
        recommendRetry: false,
      };
    }

    if (scannerMode === "upload") {
      return {
        tone: "muted",
        state: "ready",
        stateLabel: "READY",
        code: "",
        title: "Image Upload Mode",
        message: "Upload a screenshot or photo containing a ticket QR code.",
        hint: "Use clear, high-contrast images for best decode accuracy.",
        retryMessage: "If decode fails, retake image with sharper focus and better lighting.",
        recommendRetry: false,
      };
    }

    return {
      tone: "muted",
      state: "ready",
      stateLabel: "READY",
      code: "",
      title: "Manual Entry Mode",
      message: "Paste ticket reference, ticket id, URL, or raw QR payload.",
      hint: "Press Enter or click Validate Ticket.",
      retryMessage: "Use Retry Last Scan for quick re-validation.",
      recommendRetry: false,
    };
  }, [cameraError, error, isDecodingUpload, isScanning, notice, noticeTone, scanOutcome, scannerMode]);

  const summary = monitorData.summary || {};
  const realtime = monitorData.realtime || {};
  const monitorFilterMeta = monitorData.filters || {};
  const staffFilterOptions = Array.isArray(monitorFilterMeta.staff) ? monitorFilterMeta.staff : [];
  const movieFilterOptions = Array.isArray(monitorFilterMeta.movies) ? monitorFilterMeta.movies : [];
  const showFilterOptions = Array.isArray(monitorFilterMeta.shows) ? monitorFilterMeta.shows : [];
  const statusFilterOptions =
    Array.isArray(monitorFilterMeta.statuses) && monitorFilterMeta.statuses.length
      ? monitorFilterMeta.statuses
      : FALLBACK_MONITOR_STATUS_OPTIONS;
  const monitorAlerts = useMemo(() => {
    const sourceAlerts = Array.isArray(monitorData.alerts) ? monitorData.alerts : [];
    return sourceAlerts.map((alert) => buildMonitorAlertDisplay(alert));
  }, [monitorData.alerts]);
  const feedbackClass = `vendor-scanFeedback vendor-scanFeedback-${scanFeedback.tone} vendor-scanFeedback-state-${scanFeedback.state || scanFeedback.tone}`;
  const hourlyTrend = useMemo(() => {
    const fallback = Array.from({ length: 24 }, (_, index) => ({
      hour: `${String(index).padStart(2, "0")}:00`,
      total: 0,
      failed: 0,
    }));

    const source = Array.isArray(realtime.hourlyScanTrend) && realtime.hourlyScanTrend.length
      ? realtime.hourlyScanTrend
      : fallback;

    const normalized = source.map((item, index) => ({
      hour: String(item?.hour || `${String(index).padStart(2, "0")}:00`),
      total: Math.max(0, Number(item?.total || 0)),
      failed: Math.max(0, Number(item?.failed || 0)),
    }));

    const maxTotal = Math.max(1, ...normalized.map((item) => item.total));
    return normalized.map((item) => ({
      ...item,
      totalHeight: item.total > 0 ? Math.max(8, Math.round((item.total / maxTotal) * 100)) : 0,
      failedHeight: item.failed > 0 ? Math.max(5, Math.round((item.failed / maxTotal) * 100)) : 0,
    }));
  }, [realtime.hourlyScanTrend]);

  return (
    <div className="vendor-dashboard">
      <div className="d-flex flex-wrap align-items-center justify-content-between gap-3 mb-3">
        <div>
          <h2 className="mb-1">Ticket Validation</h2>
          <p className="text-muted mb-0">Track scanned tickets and detect duplicate/fraud attempts.</p>
        </div>
      </div>

      <section className="vendor-card mb-3">
        <div className="vendor-card-header">
          <div>
            <h3>Scan Ticket</h3>
            <p>Fallback modes: camera scan, manual entry, and image upload decode.</p>
          </div>
        </div>

        <div className="vendor-scanModeSwitch">
          {SCANNER_MODES.map((mode) => {
            const Icon = mode.icon;
            const active = scannerMode === mode.id;
            return (
              <button
                key={mode.id}
                type="button"
                className={`vendor-scanModeBtn ${active ? "active" : ""}`}
                onClick={() => setScannerMode(mode.id)}
                disabled={isScanning || isDecodingUpload}
              >
                <Icon size={15} />
                {mode.label}
              </button>
            );
          })}
        </div>

        {scannerMode === "manual" ? (
          <div className="d-flex gap-2 flex-wrap align-items-center mt-3">
            <input
              className="form-control"
              style={{ maxWidth: 460 }}
              placeholder="e.g. AB12CD34, 1024, URL, or raw QR payload"
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  handleManualScan();
                }
              }}
            />
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleManualScan}
              disabled={isScanning || isDecodingUpload}
            >
              <Search size={16} className="me-2" />
              {isScanning ? "Validating..." : "Validate Ticket"}
            </button>
          </div>
        ) : null}

        {scannerMode === "upload" ? (
          <div className="d-flex gap-2 flex-wrap align-items-center mt-3">
            <input
              ref={uploadInputRef}
              type="file"
              accept="image/*"
              className="form-control"
              style={{ maxWidth: 420 }}
              onChange={handleUploadSelection}
              disabled={isScanning || isDecodingUpload}
            />
            <button
              type="button"
              className="btn btn-outline-secondary"
              onClick={() => uploadInputRef.current?.click()}
              disabled={isScanning || isDecodingUpload}
            >
              <ImageUp size={16} className="me-2" />
              {isDecodingUpload ? "Decoding..." : "Choose Image"}
            </button>
          </div>
        ) : null}

        {scannerMode === "camera" ? (
          <>
            <div className="d-flex gap-2 flex-wrap align-items-center mt-3">
              <button
                type="button"
                className="btn btn-outline-secondary"
                onClick={isCameraOpen ? stopCameraScanner : () => startCameraScanner()}
                disabled={isStartingCamera || isScanning || isDecodingUpload}
              >
                {isCameraOpen ? <CameraOff size={16} className="me-2" /> : <Camera size={16} className="me-2" />}
                {isCameraOpen ? "Stop Camera" : isStartingCamera ? "Opening Camera..." : "Start Camera Scan"}
              </button>
              <button
                type="button"
                className="btn btn-outline-secondary"
                onClick={handleSwitchCamera}
                disabled={
                  isStartingCamera ||
                  isScanning ||
                  isDecodingUpload ||
                  availableCameras.length <= 1
                }
              >
                <RefreshCcw size={16} className="me-2" />
                Switch Camera
              </button>
              {activeCameraLabel ? <span className="vendor-cameraBadge">{activeCameraLabel}</span> : null}
            </div>

            {isCameraOpen || isStartingCamera ? (
              <div className="vendor-qrScanner mt-3">
                <div className="vendor-qrVideoWrap">
                  <video ref={videoRef} className="vendor-qrVideo" autoPlay playsInline muted />
                  <div className="vendor-qrGuide" aria-hidden="true" />
                </div>
                <small className="text-muted d-block mt-2">
                  Hold the ticket QR steady inside the frame. Scan triggers automatically.
                </small>
              </div>
            ) : null}
          </>
        ) : null}

        <div className={feedbackClass}>
          <div className="vendor-scanFeedbackTop">
            <span className={`vendor-scanFeedbackBadge vendor-scanFeedbackBadge-${scanFeedback.state || scanFeedback.tone}`}>
              {scanFeedback.stateLabel || "INFO"}
            </span>
            {scanFeedback.code ? <span className="vendor-scanFeedbackCode">{scanFeedback.code}</span> : null}
          </div>
          <div className="vendor-scanFeedbackTitle">{scanFeedback.title}</div>
          <p className="vendor-scanFeedbackMessage">{scanFeedback.message}</p>
          {scanFeedback.hint ? <small className="vendor-scanFeedbackHint">{scanFeedback.hint}</small> : null}
          {scanFeedback.retryMessage ? <small className="vendor-scanRetryMessage">{scanFeedback.retryMessage}</small> : null}

          <div className="vendor-scanFeedbackActions">
            <button
              type="button"
              className={`btn btn-sm ${scanFeedback.recommendRetry ? "btn-warning" : "btn-outline-secondary"}`}
              onClick={retryLastScan}
              disabled={!lastScanValue || isScanning || isDecodingUpload}
            >
              <RefreshCcw size={14} className="me-1" />
              {scanFeedback.recommendRetry ? "Retry Now" : "Retry Last Scan"}
            </button>
            <button
              type="button"
              className="btn btn-sm btn-outline-secondary"
              onClick={() => setScannerMode("manual")}
              disabled={isScanning || isDecodingUpload}
            >
              <Keyboard size={14} className="me-1" />
              Manual Entry
            </button>
            <button
              type="button"
              className="btn btn-sm btn-outline-secondary"
              onClick={() => setScannerMode("upload")}
              disabled={isScanning || isDecodingUpload}
            >
              <ImageUp size={14} className="me-1" />
              Image Upload
            </button>
          </div>
        </div>

        {scanResult ? (
          <div className="row g-2 mt-2">
            <div className="col-md-3"><strong>Reference:</strong> {scanResult.reference}</div>
            <div className="col-md-3"><strong>Ticket ID:</strong> {scanResult.ticketId || "-"}</div>
            <div className="col-md-3"><strong>Status:</strong> {scanResult.status}</div>
            <div className="col-md-3"><strong>Fraud Score:</strong> {scanResult.fraudScore}</div>
            <div className="col-md-3"><strong>Duplicate Count:</strong> {scanResult.duplicateCount || 0}</div>
            <div className="col-md-3"><strong>Total Scans:</strong> {scanResult.totalScansForTicket || 0}</div>
            <div className="col-md-3"><strong>Scanned At:</strong> {formatDateTime(scanResult.scannedAt)}</div>
            {scanResult.reason ? <div className="col-12"><strong>Reason:</strong> {scanResult.reason}</div> : null}
          </div>
        ) : null}
      </section>

      <section className="vendor-card mb-3">
        <div className="vendor-card-header">
          <div>
            <h3>Validation Summary</h3>
            <p>Real-time ticket validation and alert overview.</p>
          </div>
        </div>

        <div className="row g-2 mb-2">
          <SummaryCard icon={Clock3} label="Today Scans" value={realtime.todayScans || 0} />
          <SummaryCard icon={ShieldAlert} label="Failed Scans" value={realtime.todayFailedScans || 0} isDanger />
          <SummaryCard icon={CheckCircle2} label="Today Valid" value={realtime.todayValidScans || 0} />
          <SummaryCard icon={AlertTriangle} label="Today Duplicates" value={realtime.todayDuplicateScans || 0} isWarning />
        </div>

        <div className="vendor-hourlyTrendPanel">
          <div className="vendor-hourlyTrendHeader">
            <div className="vendor-hourlyTrendTitle">
              <BarChart3 size={16} />
              <span>Hourly Scan Trend (Today)</span>
            </div>
            <small className="text-muted">
              Failed rate: {formatPercent(realtime.todayFailedRate)} | Updated: {formatTimeLabel(realtime.updatedAt)}
            </small>
          </div>
          <div className="vendor-hourlyTrendBars" role="img" aria-label="Hourly scan trend for today">
            {hourlyTrend.map((item) => (
              <div
                key={item.hour}
                className="vendor-hourlyTrendItem"
                title={`${item.hour} | Total: ${item.total} | Failed: ${item.failed}`}
              >
                <div className="vendor-hourlyTrendStack">
                  <div
                    className="vendor-hourlyTrendBarTotal"
                    style={{ height: `${item.totalHeight}%` }}
                  />
                  <div
                    className="vendor-hourlyTrendBarFailed"
                    style={{ height: `${Math.min(item.totalHeight, item.failedHeight)}%` }}
                  />
                </div>
                <small>{item.hour.slice(0, 2)}</small>
              </div>
            ))}
          </div>
        </div>

        <div className="row g-2">
          <SummaryCard icon={Ticket} label="Total Scans" value={summary.total || 0} />
          <SummaryCard icon={Search} label="Unique Tickets" value={summary.uniqueTickets || 0} />
          <SummaryCard icon={CheckCircle2} label="Valid" value={summary.valid || 0} />
          <SummaryCard icon={AlertTriangle} label="Duplicate" value={summary.duplicate || 0} isWarning />
          <SummaryCard icon={ShieldAlert} label="Fraud/Invalid" value={(summary.fraud || 0) + (summary.invalid || 0)} isDanger />
        </div>
        <p className="text-muted mt-3 mb-0">
          Duplicate rate: {formatPercent(summary.duplicateRate)} | Risk rate: {formatPercent(summary.riskRate)}
        </p>
        <div className="vendor-monitorAlerts mt-3">
          {monitorAlerts.map((alert, index) => (
            <article
              key={`${alert.type}-${index}`}
              className={`vendor-monitorAlert vendor-monitorAlert-${alert.severity} ${alert.isTriggered ? "is-triggered" : ""}`}
            >
              <div className="vendor-monitorAlertHeader">
                <strong>{alert.title}</strong>
                <span className="vendor-monitorAlertCount">{alert.count}</span>
              </div>
              {alert.message ? <p className="vendor-monitorAlertMessage">{alert.message}</p> : null}
              {alert.details ? <small className="vendor-monitorAlertMeta">{alert.details}</small> : null}
              {alert.offenders.length ? (
                <div className="vendor-monitorAlertOffenders">
                  {alert.offenders.map((offender, offenderIndex) => (
                    <span key={`${alert.type}-offender-${offenderIndex}`} className="vendor-monitorAlertOffenderChip">
                      {offender.reference}
                      {offender.ticketId ? ` (#${offender.ticketId})` : ""}
                      {offender.duplicateAttempts > 0 ? ` x${offender.duplicateAttempts}` : ""}
                    </span>
                  ))}
                </div>
              ) : null}
            </article>
          ))}
        </div>
      </section>

      <section className="vendor-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <div>
            <h3 className="mb-0">Scan Logs</h3>
            <p className="text-muted mb-0">Filter by date, staff, status, movie, and show. Export current results to CSV.</p>
          </div>
          <button
            type="button"
            className="btn btn-outline-secondary"
            onClick={handleExportMonitorCsv}
            disabled={isExportingCsv}
          >
            <Download size={16} className="me-2" />
            {isExportingCsv ? "Exporting..." : "Export CSV"}
          </button>
        </div>

        <div className="row g-2 align-items-end mb-3">
          <div className="col-md-2 col-sm-6">
            <label className="form-label mb-1">Date</label>
            <input
              className="form-control"
              type="date"
              value={monitorFilters.date}
              onChange={(event) => updateMonitorFilter("date", event.target.value)}
            />
          </div>

          <div className="col-md-2 col-sm-6">
            <label className="form-label mb-1">Staff</label>
            <select
              className="form-select"
              value={monitorFilters.staff}
              onChange={(event) => updateMonitorFilter("staff", event.target.value)}
            >
              <option value="">All Staff</option>
              {staffFilterOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="col-md-2 col-sm-6">
            <label className="form-label mb-1">Status</label>
            <select
              className="form-select"
              value={monitorFilters.status}
              onChange={(event) => updateMonitorFilter("status", event.target.value)}
            >
              <option value="">All Statuses</option>
              {statusFilterOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="col-md-2 col-sm-6">
            <label className="form-label mb-1">Movie</label>
            <select
              className="form-select"
              value={monitorFilters.movie}
              onChange={(event) => updateMonitorFilter("movie", event.target.value)}
            >
              <option value="">All Movies</option>
              {movieFilterOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="col-md-2 col-sm-6">
            <label className="form-label mb-1">Show</label>
            <select
              className="form-select"
              value={monitorFilters.show}
              onChange={(event) => updateMonitorFilter("show", event.target.value)}
            >
              <option value="">All Shows</option>
              {showFilterOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="col-md-2 col-sm-6">
            <label className="form-label mb-1">Reference</label>
            <input
              className="form-control"
              placeholder="e.g. RACE1234"
              value={monitorFilters.reference}
              onChange={(event) => updateMonitorFilter("reference", event.target.value)}
            />
          </div>

          <div className="col-12 d-flex flex-wrap gap-2 justify-content-end">
            <button type="button" className="btn btn-primary" onClick={applyMonitorFilters} disabled={isLoading}>
              {isLoading ? "Loading..." : "Apply Filters"}
            </button>
            <button type="button" className="btn btn-outline-light" onClick={resetMonitorFilters} disabled={isLoading}>
              Reset
            </button>
          </div>
        </div>

        <div className="d-flex flex-wrap gap-2 justify-content-end align-items-center mb-3">
          <input
            className="form-control"
            style={{ maxWidth: 320 }}
            placeholder="Quick search in loaded logs"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        {monitorError ? <div className="alert alert-danger py-2 mb-3">{monitorError}</div> : null}
        {monitorNotice ? <div className="alert alert-success py-2 mb-3">{monitorNotice}</div> : null}
        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Reference</th>
                <th>Ticket ID</th>
                <th>Staff</th>
                <th>Status</th>
                <th>Movie</th>
                <th>Show</th>
                <th>Fraud Score</th>
                <th>Reason</th>
                <th>Scanned At</th>
              </tr>
            </thead>
            <tbody>
              {filteredScans.map((scan) => (
                <tr key={scan.id}>
                  <td>{scan.reference}</td>
                  <td>{scan.ticketId || "-"}</td>
                  <td>{scan.scannedByName || "Vendor Account"}</td>
                  <td>{scan.status}</td>
                  <td>{scan.movieTitle || "-"}</td>
                  <td>{scan.showLabel || "-"}</td>
                  <td>{scan.fraudScore}</td>
                  <td>{scan.reason || "-"}</td>
                  <td>{formatDateTime(scan.scannedAt)}</td>
                </tr>
              ))}
              {isLoading ? (
                <tr>
                  <td colSpan="9">Loading validation logs...</td>
                </tr>
              ) : null}
              {!isLoading && filteredScans.length === 0 ? (
                <tr>
                  <td colSpan="9">No validation logs found for the selected filters.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function SummaryCard({ icon, label, value, isWarning = false, isDanger = false }) {
  const iconNode = typeof icon === "function" ? createElement(icon, { size: 16 }) : null;
  return (
    <div className="col-md-3 col-sm-6">
      <div className={`p-3 rounded border ${isDanger ? "border-danger" : isWarning ? "border-warning" : "border-secondary"}`}>
        <div className="d-flex align-items-center gap-2 mb-1">
          {iconNode}
          <small className="text-muted">{label}</small>
        </div>
        <h4 className="mb-0">{value}</h4>
      </div>
    </div>
  );
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString();
}

function formatPercent(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) return "0.00%";
  return `${parsed.toFixed(2)}%`;
}

function formatTimeLabel(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleTimeString();
}
