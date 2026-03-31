import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, Search, ShieldAlert, Ticket } from "lucide-react";
import {
  fetchVendorTicketValidationMonitor,
  validateVendorTicket,
} from "../lib/catalogApi";

export default function VendorTicketValidation() {
  const [reference, setReference] = useState("");
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [monitorData, setMonitorData] = useState({ summary: {}, alerts: [], scans: [] });
  const [isLoading, setIsLoading] = useState(false);
  const [search, setSearch] = useState("");

  const loadMonitor = async (params = {}) => {
    setIsLoading(true);
    try {
      const data = await fetchVendorTicketValidationMonitor({ limit: 100, ...params });
      setMonitorData({
        summary: data?.summary || {},
        alerts: Array.isArray(data?.alerts) ? data.alerts : [],
        scans: Array.isArray(data?.scans) ? data.scans : [],
      });
    } catch (err) {
      setError(err.message || "Unable to load validation logs.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadMonitor();
  }, []);

  const filteredScans = useMemo(() => {
    const keyword = String(search || "").trim().toLowerCase();
    const scans = Array.isArray(monitorData.scans) ? monitorData.scans : [];
    if (!keyword) return scans;
    return scans.filter((scan) => {
      const value = [scan?.reference, scan?.status, scan?.reason]
        .map((part) => String(part || "").toLowerCase())
        .join(" ");
      return value.includes(keyword);
    });
  }, [monitorData.scans, search]);

  const handleScan = async () => {
    const nextReference = String(reference || "").trim().toUpperCase();
    if (!nextReference) {
      setError("Enter ticket reference.");
      return;
    }

    setError("");
    setNotice("");
    setScanResult(null);
    setIsScanning(true);
    try {
      const result = await validateVendorTicket(nextReference);
      setScanResult(result?.scan || null);
      setNotice(result?.message || "Scan completed.");
      await loadMonitor();
    } catch (err) {
      setError(err.message || "Scan failed.");
    } finally {
      setIsScanning(false);
    }
  };

  const summary = monitorData.summary || {};

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
            <p>Enter ticket reference from QR or printed ticket.</p>
          </div>
        </div>
        <div className="d-flex gap-2 flex-wrap align-items-center">
          <input
            className="form-control"
            style={{ maxWidth: 340 }}
            placeholder="e.g. AB12CD34"
            value={reference}
            onChange={(event) => setReference(event.target.value.toUpperCase())}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                handleScan();
              }
            }}
          />
          <button type="button" className="btn btn-primary" onClick={handleScan} disabled={isScanning}>
            <Search size={16} className="me-2" />
            {isScanning ? "Scanning..." : "Validate Ticket"}
          </button>
        </div>

        {error ? <div className="alert alert-danger mt-3">{error}</div> : null}
        {notice ? <div className="alert alert-success mt-3">{notice}</div> : null}

        {scanResult ? (
          <div className="row g-2 mt-2">
            <div className="col-md-3"><strong>Reference:</strong> {scanResult.reference}</div>
            <div className="col-md-3"><strong>Status:</strong> {scanResult.status}</div>
            <div className="col-md-3"><strong>Fraud Score:</strong> {scanResult.fraudScore}</div>
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
        <div className="row g-2">
          <SummaryCard icon={Ticket} label="Total Scans" value={summary.total || 0} />
          <SummaryCard icon={CheckCircle2} label="Valid" value={summary.valid || 0} />
          <SummaryCard icon={AlertTriangle} label="Duplicate" value={summary.duplicate || 0} isWarning />
          <SummaryCard icon={ShieldAlert} label="Fraud/Invalid" value={(summary.fraud || 0) + (summary.invalid || 0)} isDanger />
        </div>
        <div className="mt-3">
          {(monitorData.alerts || []).map((alert) => (
            <div key={alert.type} className={`alert ${alert.count > 0 ? "alert-warning" : "alert-secondary"} py-2`}>
              <strong>{alert.type === "duplicate_ticket" ? "Duplicate Ticket Alerts" : "Fraud Alerts"}:</strong>{" "}
              {alert.count || 0}
            </div>
          ))}
        </div>
      </section>

      <section className="vendor-card">
        <div className="d-flex flex-wrap gap-2 justify-content-between align-items-center mb-3">
          <h3 className="mb-0">Scan Logs</h3>
          <input
            className="form-control"
            style={{ maxWidth: 320 }}
            placeholder="Search reference/status"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <div className="vendor-table-wrap">
          <table className="vendor-table">
            <thead>
              <tr>
                <th>Reference</th>
                <th>Status</th>
                <th>Fraud Score</th>
                <th>Reason</th>
                <th>Scanned At</th>
              </tr>
            </thead>
            <tbody>
              {filteredScans.map((scan) => (
                <tr key={scan.id}>
                  <td>{scan.reference}</td>
                  <td>{scan.status}</td>
                  <td>{scan.fraudScore}</td>
                  <td>{scan.reason || "-"}</td>
                  <td>{formatDateTime(scan.scannedAt)}</td>
                </tr>
              ))}
              {!isLoading && filteredScans.length === 0 ? (
                <tr>
                  <td colSpan="5">No validation logs yet.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function SummaryCard({ icon: Icon, label, value, isWarning = false, isDanger = false }) {
  return (
    <div className="col-md-3 col-sm-6">
      <div className={`p-3 rounded border ${isDanger ? "border-danger" : isWarning ? "border-warning" : "border-secondary"}`}>
        <div className="d-flex align-items-center gap-2 mb-1">
          <Icon size={16} />
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
