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
      <div className="wf2-orderPage">
        <div className="wf2-orderPanel">Verifying payment...</div>
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
    <div className="wf2-orderPage">
      <div className="wf2-orderPanel wf2-lifecycleShell" style={{ maxWidth: 840, margin: "40px auto" }}>
        <div className="wf2-lifecycleHero">
          <span className="wf2-orderChip">Payment verified</span>
          <h2>eSewa payment success</h2>
          <p>The callback was accepted and the booking is moving toward final ticket handoff.</p>
        </div>

        {error ? <div className="wf2-lifecycleAlert wf2-lifecycleAlertDanger">{error}</div> : null}

        {!error ? (
          <div className="wf2-lifecycleGrid">
            <div className="wf2-lifecycleCard">
              <span>Verification</span>
              <strong>{verified ? "Valid" : "Invalid"}</strong>
              <p>Gateway response signature and payload were checked.</p>
            </div>
            <div className="wf2-lifecycleCard">
              <span>Gateway status</span>
              <strong>{completed ? "Complete" : statusLabel}</strong>
              <p>The gateway status is now the source of truth for this booking.</p>
            </div>
            <div className="wf2-lifecycleCard">
              <span>Booking state</span>
              <strong>{confirmed ? "Confirmed" : "Waiting"}</strong>
              <p>{confirmed ? "Ticket download can continue." : "The booking still needs completion."}</p>
            </div>
          </div>
        ) : null}

        {verification?.message ? <div className="wf2-lifecycleAlert">{verification.message}</div> : null}

        <details className="wf2-lifecycleDetails">
          <summary>Decoded response</summary>
          <pre>{JSON.stringify(verification?.decoded || decoded || {}, null, 2)}</pre>
        </details>

        <div className="wf2-lifecycleActions">
          <button className="wf2-orderPayBtn" type="button" onClick={() => navigate("/") }>
            Go Home
          </button>
          {confirmed ? (
            <button className="wf2-orderPayBtn" type="button" onClick={handleContinue}>
              Continue
            </button>
          ) : (
            <button className="wf2-orderPayBtn" type="button" onClick={() => navigate("/movies") }>
              Browse Movies
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
