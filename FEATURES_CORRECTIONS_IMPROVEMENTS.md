# Mero Ticket Audit

## 1. Mistakes & Weaknesses


## 2. Missing Real-World Logic

- No settlement lifecycle for vendor payouts.
- No chargeback/dispute handling.
- No enforced manual-review gate for risky bookings.
- No audit log for admin changes to commission, movies, or wallet adjustments.
- No periodic reconciliation job to detect payment/gateway mismatches.
- No KYC or bank-account validation for vendor withdrawals.
- No clear payout failure/retry flow.

## 3. Improvements

### Backend


### Database Design



### API Optimization


### Frontend UX/UI


### Architecture


## 4. Feature Suggestions

- Wallet and withdrawal system: payout schedule, minimum withdrawal threshold, payout history, failed payout retries, and destination verification.
- Loyalty system: tier expiry, redemption caps, anti-abuse checks, and better reward visibility.
- Referral system: self-referral detection, device/IP heuristics, hold period before rewards become spendable.
- Dynamic pricing: admin preview, explainability, and rule simulation before publishing.
- Subscription plans: renewal reminders, pause/resume, expiry handling, and compatibility rules with coupons/referrals.
- Corporate booking: invoices, bulk seat holds, organization-level billing, and partial payment settlement.
- Vendor analytics dashboard: revenue by show, occupancy by slot, cancellation rate, refund rate, and payout pending.
- AI recommendations: use for discovery and personalization only, not for settlement or risk decisions.

## 5. Earnings & Payment Logic Review


## 6. Scalability & Performance

- At 10k+ users, dashboard queries and repeated aggregates will become expensive without caching or rollups.
- Seat reservation is already on the right track with locks and expiration, but cleanup should be job-based, not request-based.
- Use Redis for cacheable summaries and precomputed counts.
- Add background workers for reconciliation, notifications, analytics, and stale pending cleanup.
- Consider archival or partitioning once booking and notification tables grow large.

## 7. Security Improvements

- Strengthen authentication with short-lived access tokens and refresh/revocation support.
- Never trust client-supplied totals or status values.
- Rate-limit payment verification, OTP, ticket scan, login, and withdrawal endpoints.
- Validate money amounts, transaction references, and status transitions server-side.
- Log suspicious transitions and repeated callback attempts.
- Keep secrets out of request-visible flows and enforce HTTPS-only transport.

## 8. Final Verdict

- The project is a solid MVP, but not production-ready for real money at scale.
- It has good foundations: seat locking, refund hooks, wallet concepts, and server-side payment verification.
- The biggest risk is the financial/state model, not the UI.

### Top 5 Critical Fixes

1. Stop creating paid-looking ticket records before payment confirmation.
2. Add durable payment transaction IDs and a real payment state machine.
3. Enforce fraud/manual-review decisions.
4. Replace wallet balance clamping with a real immutable ledger.
5. Add vendor movie moderation if vendors can submit catalog items.

## Practical Priority Order

1. Fix payment and ticket finalization flow.
2. Normalize booking, payment, refund, and withdrawal statuses.
3. Add ledger and reconciliation support for wallet/accounting.
4. Add moderation for vendor-submitted catalog content.
5. Move dashboard aggregates and side effects into background jobs.
