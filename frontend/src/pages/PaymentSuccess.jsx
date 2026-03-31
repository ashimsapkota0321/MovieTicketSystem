import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { verifyEsewaPayment } from "../lib/catalogApi";

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
  const transactionUuid =
    query.get("transaction_uuid") || query.get("transactionUuid") || "";
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
      <div className="wf2-orderPage">
        <div className="wf2-orderPanel">Verifying payment...</div>
      </div>
    );
  }

  const verified = Boolean(verification?.verified);
  const confirmed = Boolean(verification?.confirmed);
  const completed = Boolean(verification?.is_complete);
  const statusLabel =
    verification?.status ||
    verification?.status_check?.status ||
    "UNKNOWN";
  const orderPayload =
    verification?.order || verification?.ticket?.payload?.order || null;
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
    <div className="wf2-orderPage">
      <div className="wf2-orderPanel" style={{ maxWidth: 720, margin: "40px auto" }}>
        <h2>eSewa Payment Success Callback</h2>
        {error ? <p style={{ color: "#ff6b6b" }}>{error}</p> : null}

        {!error ? (
          <div style={{ marginTop: 12 }}>
            <p>
              Verification: <strong>{verified ? "VALID" : "INVALID"}</strong>
            </p>
            <p>
              Status: <strong>{completed ? "COMPLETE" : statusLabel}</strong>
            </p>
            <p>
              Booking: <strong>{confirmed ? "CONFIRMED" : "NOT CONFIRMED"}</strong>
            </p>
            {verification?.message ? <p>{verification.message}</p> : null}
          </div>
        ) : null}

        <div style={{ marginTop: 16 }}>
          <h4>Decoded Response</h4>
          <pre style={{ whiteSpace: "pre-wrap" }}>
            {JSON.stringify(verification?.decoded || decoded || {}, null, 2)}
          </pre>
        </div>

        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          <button className="wf2-orderPayBtn" type="button" onClick={() => navigate("/")}>
            Go Home
          </button>
          {confirmed ? (
            <button className="wf2-orderPayBtn" type="button" onClick={handleContinue}>
              Continue
            </button>
          ) : (
            <button
              className="wf2-orderPayBtn"
              type="button"
              onClick={() => navigate("/movies")}
            >
              Browse Movies
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
