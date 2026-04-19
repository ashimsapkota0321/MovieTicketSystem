import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { verifyEsewaPayment } from "../lib/catalogApi";
import { CheckCircle } from "lucide-react";

function decodeEsewaData(dataValue) {
  if (!dataValue) return null;
  try {
    const normalized = String(dataValue)
      .trim()
      .replace(/\s/g, "+")
      .replace(/-/g, "+")
      .replace(/_/g, "/");
    const padded = normalized.padEnd(
      normalized.length + ((4 - (normalized.length % 4)) % 4),
      "="
    );
    const decoded = atob(padded);
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}

export default function PaymentSuccess() {
  const location = useLocation();
  const navigate = useNavigate();
  const [verification, setVerification] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const query = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const dataValue = query.get("data") || "";
  const transactionUuid = query.get("transaction_uuid") || query.get("transactionUuid") || "";
  const decoded = useMemo(() => decodeEsewaData(dataValue), [dataValue]);

  useEffect(() => {
    let mounted = true;

    const verify = async () => {
      if (!dataValue && !transactionUuid) {
        setError("Missing eSewa callback payload.");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError("");
      try {
        const result = await verifyEsewaPayment({
          data: dataValue || undefined,
          transaction_uuid: transactionUuid || undefined,
        });
        if (!mounted) return;
        setVerification(result);
      } catch (err) {
        if (!mounted) return;
        setError(err?.message || "Unable to verify eSewa payment.");
      } finally {
        if (mounted) setLoading(false);
      }
    };

    verify();
    return () => {
      mounted = false;
    };
  }, [dataValue, transactionUuid]);


  if (loading) {
    return (
      <div style={{ minHeight: "80vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--page-bg, #181a20)" }}>
        <div style={{ background: "#23232a", borderRadius: 20, boxShadow: "0 4px 32px rgba(0,0,0,0.18)", padding: "48px 32px", maxWidth: 420, width: "100%", textAlign: "center" }}>
          <div style={{ color: "#bfc9d8", fontSize: 18 }}>Verifying payment...</div>
        </div>
      </div>
    );
  }

  const verified = Boolean(verification?.verified);
  const confirmed = Boolean(verification?.confirmed);
  const completed = Boolean(verification?.is_complete);
  const statusLabel = verification?.status || verification?.status_check?.status || "UNKNOWN";
  const orderPayload = verification?.order || verification?.ticket?.payload?.order || null;
  const ticketPayload = verification?.ticket || null;

  const handleContinue = () => {
    if (!confirmed || !ticketPayload) return;
    navigate("/thank-you", {
      state: {
        order: orderPayload || {},
        ticket: ticketPayload,
      },
    });
  };

  return (
    <div style={{ minHeight: "80vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--page-bg, #181a20)" }}>
      <div style={{ background: "#23232a", borderRadius: 20, boxShadow: "0 4px 32px rgba(0,0,0,0.18)", padding: "48px 32px", maxWidth: 420, width: "100%", textAlign: "center" }}>
        <CheckCircle size={64} color="#0ec3e0" style={{ marginBottom: 16 }} />
        <h2 style={{ color: "#fff", marginBottom: 8 }}>Thank You!</h2>
        <div style={{ color: "#bfc9d8", fontSize: 18, marginBottom: 24 }}>
          {error ? (
            <span style={{ color: "#ff6b6b" }}>{error}</span>
          ) : confirmed ? (
            <>Your payment was successful.<br />Your booking is confirmed.</>
          ) : (
            <>Your payment was received, but booking is not yet confirmed.<br />Please check your ticket or contact support.</>
          )}
        </div>
        <div style={{ display: "flex", gap: 12, justifyContent: "center", marginTop: 24 }}>
          <button
            className="wf2-orderPayBtn"
            style={{ minWidth: 120 }}
            onClick={() => navigate("/")}
          >
            Go Home
          </button>
          {confirmed ? (
            <button
              className="wf2-orderPayBtn wf2-btnSecondary"
              style={{ minWidth: 120 }}
              onClick={handleContinue}
            >
              Download Ticket
            </button>
          ) : (
            <button
              className="wf2-orderPayBtn wf2-btnSecondary"
              style={{ minWidth: 120 }}
              onClick={() => navigate("/movies")}
            >
              Browse Movies
            </button>
          )}
        </div>
        <details style={{ marginTop: 32, color: "#bfc9d8", textAlign: "left" }}>
          <summary>Decoded response</summary>
          <pre style={{ whiteSpace: "pre-wrap", color: "#bfc9d8" }}>{JSON.stringify(verification?.decoded || decoded || {}, null, 2)}</pre>
        </details>
      </div>
    </div>
  );
}
