import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { verifyUserWalletTopupEsewa } from "../lib/catalogApi";

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

export default function WalletTopupSuccess() {
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
        const result = await verifyUserWalletTopupEsewa({
          data: dataValue || undefined,
          transaction_uuid: transactionUuid || undefined,
        });
        if (!mounted) return;
        setVerification(result || null);
      } catch (err) {
        if (!mounted) return;
        setError(err?.message || "Unable to verify wallet top-up payment.");
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
        <div className="wf2-orderPanel">Verifying wallet top-up...</div>
      </div>
    );
  }

  const credited = Boolean(verification?.credited);
  const alreadyProcessed = Boolean(verification?.already_processed);
  const walletBalance = Number(verification?.wallet?.balance || 0);
  const creditedAmount = Number(verification?.transaction?.amount || 0);

  return (
    <div className="wf2-orderPage">
      <div className="wf2-orderPanel" style={{ maxWidth: 720, margin: "40px auto" }}>
        <h2>{credited ? "Wallet Top-up Successful" : "Top-up Verification Pending"}</h2>

        {error ? <p style={{ color: "#ff6b6b" }}>{error}</p> : null}

        {!error ? (
          <div style={{ marginTop: 12 }}>
            <p>
              Credit Status: <strong>{credited ? "CREDITED" : "NOT CREDITED"}</strong>
            </p>
            {creditedAmount > 0 ? (
              <p>
                Added Amount: <strong>NPR {creditedAmount.toLocaleString()}</strong>
              </p>
            ) : null}
            {credited ? (
              <p>
                Current Wallet Balance: <strong>NPR {walletBalance.toLocaleString()}</strong>
              </p>
            ) : null}
            {verification?.message ? <p>{verification.message}</p> : null}
            {alreadyProcessed ? <p>This payment was already processed earlier.</p> : null}
          </div>
        ) : null}

        <div style={{ marginTop: 16 }}>
          <h4>Decoded Response</h4>
          <pre style={{ whiteSpace: "pre-wrap" }}>
            {JSON.stringify(verification?.decoded || decoded || {}, null, 2)}
          </pre>
        </div>

        <div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
          <button
            className="wf2-orderPayBtn"
            type="button"
            onClick={() => navigate("/referral/wallet")}
          >
            Go to Wallet
          </button>
          <button className="wf2-orderPayBtn" type="button" onClick={() => navigate("/")}>
            Go Home
          </button>
        </div>
      </div>
    </div>
  );
}
