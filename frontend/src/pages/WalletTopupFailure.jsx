import React, { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { verifyUserWalletTopupEsewa } from "../lib/catalogApi";

export default function WalletTopupFailure() {
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

		const verifyPendingTopup = async () => {
			if (!dataValue && !transactionUuid) {
				if (!mounted) return;
				setMessage("Payment was not completed. Try top-up again.");
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
				setMessage(result?.message || "Payment was not completed. Try top-up again.");
			} catch (err) {
				if (!mounted) return;
				setError(err?.message || "Unable to process payment callback.");
			} finally {
				if (mounted) setLoading(false);
			}
		};

		verifyPendingTopup();
		return () => {
			mounted = false;
		};
	}, [dataValue, transactionUuid]);

	const credited = Boolean(verification?.credited);

	return (
		<div className="wf2-orderPage">
			<div className="wf2-orderPanel" style={{ maxWidth: 640, margin: "40px auto" }}>
				<h2>{credited ? "Wallet Top-up Received" : "Wallet Top-up Failed"}</h2>
				{loading ? <p>Checking payment status...</p> : null}
				{!loading && !error ? <p>{message || "Your eSewa payment was not completed."}</p> : null}
				{error ? <p style={{ color: "#ff6b6b" }}>{error}</p> : null}

				<div style={{ display: "flex", gap: 10, marginTop: 16, flexWrap: "wrap" }}>
					<button
						className="wf2-orderPayBtn"
						type="button"
						onClick={() => navigate("/referral/wallet")}
					>
						Go to Wallet
					</button>
					{!credited ? (
						<button
							className="wf2-orderPayBtn"
							type="button"
							onClick={() => navigate("/referral/wallet")}
						>
							Try Again
						</button>
					) : null}
					<button className="wf2-orderPayBtn" type="button" onClick={() => navigate("/")}>
						Go Home
					</button>
				</div>
			</div>
		</div>
	);
}
