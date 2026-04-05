import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { verifyEsewaPayment } from "../lib/catalogApi";

export default function PaymentFailure() {
  const location = useLocation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [verification, setVerification] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const query = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const dataValue = query.get("data") || "";
  const transactionUuid =
    query.get("transaction_uuid") || query.get("transactionUuid") || "";

  useEffect(() => {
    let mounted = true;

    const verifyPendingPayment = async () => {
      if (!dataValue && !transactionUuid) {
        if (!mounted) return;
        setMessage("Payment was not completed. Continue your booking and try payment again.");
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
        setVerification(result || null);
        setMessage(
          result?.message ||
            "Payment was not completed. Continue your booking and try payment again."
        );
      } catch (err) {
        if (!mounted) return;
        setError(err?.message || "Unable to process payment failure callback.");
      } finally {
        if (mounted) setLoading(false);
      }
    };

    verifyPendingPayment();
    return () => {
      mounted = false;
    };
  }, [dataValue, transactionUuid]);

  const confirmed = Boolean(verification?.confirmed);
  const orderPayload = verification?.order || verification?.ticket?.payload?.order || null;
  const ticketPayload = verification?.ticket || null;

  return (
    <div className="wf2-orderPage">
      <div className="wf2-orderPanel" style={{ maxWidth: 640, margin: "40px auto" }}>
        <h2>{confirmed ? "Payment Received" : "Payment Failed"}</h2>
        {loading ? <p>Checking payment status...</p> : null}
        {!loading && !error ? (
          <p>{message || "Your eSewa payment was not completed. Please try again."}</p>
        ) : null}
        {error ? <p style={{ color: "#ff6b6b" }}>{error}</p> : null}
        <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
          {confirmed && ticketPayload ? (
            <button
              className="wf2-orderPayBtn"
              type="button"
              onClick={() =>
                navigate("/thank-you", {
                  state: {
                    order: orderPayload,
                    ticket: ticketPayload,
                  },
                })
              }
            >
              Continue
            </button>
          ) : null}
          {!confirmed && orderPayload ? (
            <button
              className="wf2-orderPayBtn"
              type="button"
              onClick={() =>
                navigate("/order-confirm", {
                  state: orderPayload,
                })
              }
            >
              Continue Booking
            </button>
          ) : null}
          <button className="wf2-orderPayBtn" type="button" onClick={() => navigate(-1)}>
            Try Again
          </button>
          <button className="wf2-orderPayBtn" type="button" onClick={() => navigate("/")}>
            Go Home
          </button>
        </div>
      </div>
    </div>
  );
}
