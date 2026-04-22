import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { verifyEsewaPayment } from "../lib/catalogApi";
import { CheckCircle, RefreshCw } from "lucide-react";
import "../css/orderConfirm.css";

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
  const redirectedRef = useRef(false);
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

  const confirmed = Boolean(verification?.confirmed);
  const orderPayload = verification?.order || verification?.ticket?.payload?.order || null;
  const ticketPayload = verification?.ticket || null;

  useEffect(() => {
    if (!confirmed || !ticketPayload || redirectedRef.current) {
      return;
    }
    redirectedRef.current = true;
    navigate("/thank-you", {
      replace: true,
      state: {
        order: orderPayload || {},
        ticket: ticketPayload,
      },
    });
  }, [confirmed, navigate, orderPayload, ticketPayload]);


  if (loading) {
    return (
      <div className="wf2-thankyouPage">
        <div className="wf2-thankyouContainer" style={{ maxWidth: 760 }}>
          <div className="wf2-thankyouHero">
            <RefreshCw size={34} style={{ animation: "wf2Spin 1.1s linear infinite" }} />
            <h1 className="wf2-thankyouTitle" style={{ fontSize: "clamp(24px, 4vw, 36px)" }}>
              Verifying Payment
            </h1>
            <p className="wf2-thankyouSubtext">
              Please wait while we confirm your eSewa transaction and prepare your ticket.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const statusLabel = verification?.status || verification?.status_check?.status || "UNKNOWN";
  const verified = Boolean(verification?.verified);
  const completed = Boolean(verification?.is_complete);

  return (
    <div className="wf2-thankyouPage">
      <div className="wf2-thankyouContainer" style={{ maxWidth: 760 }}>
        <section className="wf2-thankyouHero">
          <div className="wf2-thankyouCheck">
            <CheckCircle size={34} />
          </div>
          <h1 className="wf2-thankyouTitle" style={{ fontSize: "clamp(24px, 4vw, 38px)" }}>
            {error ? "Payment Verification Failed" : confirmed ? "Payment Verified" : "Payment Received"}
          </h1>
          <p className="wf2-thankyouSubtext">
            {error
              ? error
              : confirmed
                ? "Your booking is confirmed. Redirecting you to the Thank You page..."
                : "Your payment was received, but booking confirmation is still in progress."}
          </p>
        </section>

        <section className="wf2-lifecycleShell">
          <div className="wf2-lifecycleGrid wf2-thankyouLifecycleGrid">
            <article className="wf2-lifecycleCard">
              <span>Verification</span>
              <strong>{verified ? "Verified" : "Pending"}</strong>
              <p>Server-side signature validation and status check.</p>
            </article>
            <article className="wf2-lifecycleCard">
              <span>Gateway Status</span>
              <strong>{statusLabel}</strong>
              <p>Latest transaction state from eSewa response.</p>
            </article>
            <article className="wf2-lifecycleCard">
              <span>Booking</span>
              <strong>{confirmed ? "Confirmed" : completed ? "Processing" : "Awaiting"}</strong>
              <p>Ticket creation and booking sync status.</p>
            </article>
          </div>

          <div className={`wf2-lifecycleAlert ${error ? "wf2-lifecycleAlertDanger" : confirmed ? "wf2-lifecycleAlertSuccess" : "wf2-lifecycleAlertWarning"}`}>
            {error
              ? "We could not complete verification right now. You can retry or check your tickets from profile."
              : confirmed
                ? "Verification complete. You will be redirected automatically."
                : "Payment was captured, but confirmation is not ready yet. Please retry in a few seconds."}
          </div>

          <div className="wf2-lifecycleActions">
            <button className="wf2-thankyouBtnPrimary" onClick={() => navigate("/")}>Go Home</button>
            <button className="wf2-thankyouBtnGhost" onClick={() => navigate("/movies")}>Browse Movies</button>
            <button className="wf2-thankyouBtnGhost" onClick={() => window.location.reload()}>Retry Check</button>
          </div>

          <details className="wf2-lifecycleDetails">
            <summary>Decoded response</summary>
            <pre>{JSON.stringify(verification?.decoded || decoded || {}, null, 2)}</pre>
          </details>
        </section>
      </div>
    </div>
  );
}
