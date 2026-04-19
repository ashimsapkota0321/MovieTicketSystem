import { useState, useEffect } from "react";
import { Send } from "lucide-react";
import { requestVendorWithdrawal, fetchVendorWalletBalance } from "../lib/catalogApi";

function formatMoney(value) {
  const amount = Number(value || 0);
  return `NPR ${amount.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

export default function VendorWithdrawal() {
  const [phoneNumber, setPhoneNumber] = useState("");
  const [amount, setAmount] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [otpStep, setOtpStep] = useState(false);
  const [loading, setLoading] = useState(false);
  const [wallet, setWallet] = useState(null);
  const [withdrawalHistory, setWithdrawalHistory] = useState([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [walletLoading, setWalletLoading] = useState(true);

  useEffect(() => {
    loadWalletData();
  }, []);

  const loadWalletData = async () => {
    try {
      setWalletLoading(true);
      const data = await fetchVendorWalletBalance();
      if (data) {
        setWallet(data?.wallet || data);
        setWithdrawalHistory(Array.isArray(data?.withdrawal_history) ? data.withdrawal_history : []);
      }
    } catch (err) {
      console.error("Error loading wallet:", err);
    } finally {
      setWalletLoading(false);
    }
  };

  const handleWithdraw = async (e) => {
    e.preventDefault();
    setMessage("");
    setError("");

    try {
      setLoading(true);
      if (!otpStep) {
        if (!phoneNumber.trim()) {
          setError("Phone number is required");
          return;
        }
        if (!/^9\d{9}$/.test(phoneNumber.replace(/\D/g, ""))) {
          setError("Enter a valid Nepali phone number (10 digits, starting with 9)");
          return;
        }
        if (!amount || Number(amount) <= 0) {
          setError("Enter a valid withdrawal amount");
          return;
        }
        if (Number(amount) > (wallet?.available_balance || wallet?.availableBalance || 0)) {
          setError("Insufficient balance for this withdrawal");
          return;
        }

        const result = await requestVendorWithdrawal({
          amount: parseFloat(amount),
          phone_number: phoneNumber.replace(/\D/g, ""),
          payment_method: "ESEWA",
        });

        if (result?.requires_otp) {
          setOtpStep(true);
          setMessage(result?.message || "OTP sent to your email.");
        } else {
          setMessage(result?.message || "Withdrawal submitted.");
          setPhoneNumber("");
          setAmount("");
          setOtpCode("");
          setOtpStep(false);
          setTimeout(() => loadWalletData(), 1000);
        }
      } else {
        if (!/^\d{6}$/.test(String(otpCode || "").trim())) {
          setError("Enter 6-digit OTP sent to your email");
          return;
        }

        const result = await requestVendorWithdrawal({ otp: String(otpCode).trim() });
        setMessage(result?.message || "Payment successful.");
        setPhoneNumber("");
        setAmount("");
        setOtpCode("");
        setOtpStep(false);
        setTimeout(() => loadWalletData(), 1000);
      }
    } catch (err) {
      setError(err?.message || "Withdrawal failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="vendor-dashboard">
      <div className="revenue-head">
        <div>
          <h2 className="mb-1">eSewa Withdrawal</h2>
          <p className="text-muted mb-0">Phone number and amount हाल्नुहोस्, OTP verify गरेपछि payment complete हुन्छ।</p>
        </div>
      </div>

      {error && (
        <section className="vendor-card alert alert-danger">
          {error}
        </section>
      )}

      {message && (
        <section className="vendor-card alert alert-success">
          {message}
        </section>
      )}

      {walletLoading ? (
        <section className="vendor-card">
          <p className="text-muted mb-0">Loading wallet data...</p>
        </section>
      ) : (
        <div className="vendor-grid-2">
          <section className="vendor-card">
            <div className="vendor-card-header">
              <div>
                <h3>{otpStep ? "Verify OTP" : "Simple Withdrawal"}</h3>
                <p>{otpStep ? "Email मा आएको OTP राखेर withdrawal complete गर्नुहोस्।" : "Phone and amount हालेर OTP request गर्नुहोस्।"}</p>
              </div>
            </div>

            <form onSubmit={handleWithdraw} className="row g-3">
              <div className="col-md-6">
                <label className="form-label">Phone Number</label>
                <div className="input-group">
                  <span className="input-group-text">+977</span>
                  <input
                    type="tel"
                    className="form-control"
                    placeholder="98XXXXXXXX"
                    value={phoneNumber}
                    onChange={(e) => setPhoneNumber(e.target.value)}
                    maxLength="15"
                    disabled={loading || otpStep}
                  />
                </div>
              </div>

              <div className="col-md-6">
                <label className="form-label">Amount</label>
                <div className="input-group">
                  <span className="input-group-text">NPR</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    className="form-control"
                    placeholder="0.00"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    disabled={loading || otpStep}
                  />
                </div>
              </div>

              {otpStep ? (
                <div className="col-md-6">
                  <label className="form-label">OTP</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="6-digit OTP"
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                    maxLength="6"
                    disabled={loading}
                  />
                </div>
              ) : null}

              <div className="col-12">
                <small className="text-muted">
                  Available balance: {formatMoney(wallet?.available_balance || wallet?.availableBalance || 0)}
                </small>
              </div>

              <div className="col-12">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={loading}
                >
                  <Send size={16} className="me-2" />
                  {loading ? "Processing..." : otpStep ? "Verify OTP & Withdraw" : "Send OTP"}
                </button>
                {otpStep ? (
                  <button
                    type="button"
                    className="btn btn-outline-secondary ms-2"
                    disabled={loading}
                    onClick={() => {
                      setOtpStep(false);
                      setOtpCode("");
                      setMessage("");
                      setError("");
                    }}
                  >
                    Edit details
                  </button>
                ) : null}
              </div>
            </form>
          </section>

          <section className="vendor-card">
            <div className="vendor-card-header">
              <div>
                <h3>Withdrawal Records</h3>
                <p>Your latest withdrawal history.</p>
              </div>
            </div>

            {withdrawalHistory.length === 0 ? (
              <p className="text-muted mb-0">No withdrawal records yet.</p>
            ) : (
              <div className="table-responsive">
                <table className="table table-sm mb-0">
                  <thead className="table-light">
                    <tr>
                      <th>Amount</th>
                      <th>Status</th>
                      <th>Date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {withdrawalHistory.slice(0, 10).map((item) => (
                      <tr key={item.id}>
                        <td>{formatMoney(item.amount || 0)}</td>
                        <td>{String(item.status || "-").toUpperCase()}</td>
                        <td>{item.created_at ? new Date(item.created_at).toLocaleString() : "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
