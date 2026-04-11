import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { initiateUserWalletTopupEsewa } from "../lib/catalogApi";

const ESEWA_FORM_URL = "https://rc-epay.esewa.com.np/api/epay/main/v2/form";

export default function WalletTopupEsewaCheckout() {
  const navigate = useNavigate();
  const location = useLocation();
  const formRef = useRef(null);
  const query = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const state = location?.state || {};
  const amount = Number(state?.amount ?? query.get("amount") ?? 0);

  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const successUrl = useMemo(() => {
    if (typeof window === "undefined") return "";
    return `${window.location.origin}/wallet/topup/success`;
  }, []);

  const failureUrl = useMemo(() => {
    if (typeof window === "undefined") return "";
    return `${window.location.origin}/wallet/topup/failure`;
  }, []);

  useEffect(() => {
    let mounted = true;

    const loadSignature = async () => {
      if (!Number.isFinite(amount) || amount <= 0) {
        setError("Enter a valid top-up amount.");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError("");
      try {
        const response = await initiateUserWalletTopupEsewa({
          amount,
          success_url: successUrl,
          failure_url: failureUrl,
        });
        if (!mounted) return;
        setPayload(response || null);
      } catch (err) {
        if (!mounted) return;
        setError(err?.message || "Unable to initialize wallet top-up.");
      } finally {
        if (mounted) setLoading(false);
      }
    };

    loadSignature();
    return () => {
      mounted = false;
    };
  }, [amount, failureUrl, successUrl]);

  if (loading) {
    return (
      <div className="wf2-orderPage">
        <div className="wf2-orderPanel">Initializing wallet top-up payment...</div>
      </div>
    );
  }

  if (error || !payload) {
    return (
      <div className="wf2-orderPage">
        <div className="wf2-orderPanel" style={{ maxWidth: 640, margin: "40px auto" }}>
          <h3>Wallet Top-up Error</h3>
          <p>{error || "Missing payment payload."}</p>
          <button className="wf2-orderPayBtn" type="button" onClick={() => navigate(-1)}>
            Go Back
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="wf2-orderPage">
      <div className="wf2-orderPanel" style={{ maxWidth: 640, margin: "40px auto" }}>
        <h2 style={{ marginBottom: 12 }}>Top Up Wallet with eSewa</h2>
        <p style={{ marginBottom: 20 }}>
          Amount: <strong>NPR {payload.total_amount}</strong>
        </p>

        <form ref={formRef} method="POST" action={payload.form_url || ESEWA_FORM_URL}>
          <input type="hidden" name="amount" value={payload.amount} />
          <input type="hidden" name="tax_amount" value={payload.tax_amount} />
          <input type="hidden" name="total_amount" value={payload.total_amount} />
          <input type="hidden" name="transaction_uuid" value={payload.transaction_uuid} />
          <input type="hidden" name="product_code" value={payload.product_code} />
          <input
            type="hidden"
            name="product_service_charge"
            value={payload.product_service_charge}
          />
          <input
            type="hidden"
            name="product_delivery_charge"
            value={payload.product_delivery_charge}
          />
          <input type="hidden" name="success_url" value={payload.success_url || successUrl} />
          <input type="hidden" name="failure_url" value={payload.failure_url || failureUrl} />
          <input
            type="hidden"
            name="signed_field_names"
            value={payload.signed_field_names}
          />
          <input type="hidden" name="signature" value={payload.signature} />

          <button className="wf2-orderPayBtn" type="submit">
            Continue to eSewa
          </button>
        </form>
      </div>
    </div>
  );
}
