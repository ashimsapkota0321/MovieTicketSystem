# Mero Ticket Main Critical Testing Checklist (80 Tests)

## A. Authentication and Access Control

Testing 1 - [Black Box] Login with wrong credentials is rejected.
Testing 2 - [Black Box] Login with correct email and password succeeds.
Testing 3 - [Black Box] Login with correct phone number and password succeeds.
Testing 4 - [Black Box] Login with correct username and password succeeds.
Testing 5 - [Black Box] Login submit with empty fields shows inline required errors.
Testing 6 - [Black Box] Login with invalid email format is blocked.
Testing 7 - [Black Box] Login with invalid phone/username pattern is blocked.
Testing 8 - [Integration] Remember Me enabled persists login after browser restart.
Testing 9 - [Integration] Remember Me disabled does not persist session after browser restart.
Testing 10 - [Black Box] Logout clears token/session and redirects to login.
Testing 11 - [Security] Unauthenticated user opening protected customer route is redirected.
Testing 12 - [Security] Customer cannot access admin routes.
Testing 13 - [Security] Customer cannot access vendor routes.
Testing 14 - [Security] Vendor cannot access admin routes.

## B. Registration and OTP Verification

Testing 15 - [Black Box] Register with all valid required fields succeeds.
Testing 16 - [Black Box] Register with missing first name is blocked.
Testing 17 - [Black Box] Register with missing last name is blocked.
Testing 18 - [Black Box] Register with invalid email format is blocked.
Testing 19 - [Black Box] Register with invalid phone number format is blocked.
Testing 20 - [Black Box] Register with weak password (rule failure) is blocked.
Testing 21 - [Black Box] Register with mismatched confirm password is blocked.
Testing 22 - [Black Box] Register with terms unchecked is blocked.
Testing 23 - [Black Box] Register OTP request with valid email succeeds.
Testing 24 - [Black Box] Register OTP request with invalid email is blocked.
Testing 25 - [Black Box] Register OTP verify with wrong code fails.
Testing 26 - [Black Box] Register OTP verify with expired code fails.
Testing 27 - [Black Box] Register OTP verify success marks user as verified.
Testing 28 - [Black Box] Register submit without OTP verification is blocked.
Testing 29 - [Black Box] Register with duplicate email is blocked by backend.
Testing 30 - [Black Box] Register with duplicate phone is blocked by backend.
Testing 31 - [Black Box] Register with valid referral code applies correctly.
Testing 32 - [Black Box] Register with invalid referral code shows controlled error.
Testing 33 - [Regression] Register Sign Up button remains clickable and shows inline errors for empty form.
Testing 34 - [Regression] Register password requirement checklist updates live as user types.

## C. Forgot Password and Account Recovery

Testing 35 - [Black Box] Forgot password OTP request with valid email succeeds.
Testing 36 - [Black Box] Forgot password OTP request with invalid email is blocked.
Testing 37 - [Black Box] Forgot password OTP verify with wrong OTP fails.
Testing 38 - [Black Box] Forgot password OTP verify with expired OTP fails.
Testing 39 - [Black Box] Forgot password resend OTP before cooldown is blocked.
Testing 40 - [Black Box] Forgot password resend OTP after cooldown succeeds.
Testing 41 - [Black Box] Reset password with weak password is blocked.
Testing 42 - [Black Box] Reset password with mismatched confirm password is blocked.
Testing 43 - [Black Box] Reset password with valid OTP and strong password succeeds.
Testing 44 - [Regression] After reset success, login works with new password and fails with old password.
Testing 45 - [Regression] Forgot password step navigation clears stale error/success states.

## D. Catalog, Navigation, and Discovery

Testing 46 - [Black Box] Home page loads now-showing/hero content without crash.
Testing 47 - [Black Box] Movies page list loads correctly from API data.
Testing 48 - [Black Box] Movies page search by title returns expected results.
Testing 49 - [Black Box] Movie details page with valid movie ID loads complete data.
Testing 50 - [Black Box] Movie details page with invalid movie ID shows fallback/not-found.
Testing 51 - [Black Box] Movie schedule page loads available shows for selected movie.
Testing 52 - [Black Box] Cinema page route and vendor-specific schedule route load correctly.
Testing 53 - [Black Box] Public navigation links (Home/Movies/Schedules/Cinemas) route correctly.

## E. Booking, Seats, and Checkout Core

Testing 54 - [Security] Seat selection page blocks unauthenticated access.
Testing 55 - [Black Box] Seat map loads correctly for valid showtime.
Testing 56 - [Black Box] Already booked seats are non-selectable.
Testing 57 - [Black Box] Selecting seats updates subtotal instantly.
Testing 58 - [Black Box] Deselecting seats updates subtotal correctly.
Testing 59 - [Concurrency] Seat lock timeout releases seats after expiry.
Testing 60 - [Concurrency] Two users selecting same seat: only one can confirm.
Testing 61 - [Black Box] Checkout is blocked when no seat is selected.
Testing 62 - [Black Box] Food add/remove updates order total correctly.
Testing 63 - [Black Box] Valid coupon applies expected discount.
Testing 64 - [Black Box] Invalid/expired coupon is rejected with message.
Testing 65 - [Integration] Order summary totals (seat + food - discount) match backend calculation.
Testing 66 - [Regression] Duplicate checkout submit on slow network does not create duplicate orders.

## F. Payment, Wallet, Ticket, and History

Testing 67 - [Integration] eSewa success callback confirms booking.
Testing 68 - [Integration] eSewa failure callback keeps booking/payment unconfirmed.
Testing 69 - [Reliability] Duplicate payment callback is idempotent (no duplicate ticket/booking).
Testing 70 - [Black Box] Wallet top-up success updates wallet balance.
Testing 71 - [Black Box] Wallet top-up failure leaves wallet balance unchanged.
Testing 72 - [Black Box] Ticket download is available only for successful payment.
Testing 73 - [Black Box] Downloaded ticket shows correct booking details and QR data.
Testing 74 - [Black Box] Booking history displays latest successful booking.
Testing 75 - [Black Box] Referral wallet shows correct credit/debit balance changes.

## G. Admin, Vendor, and Advanced Feature Integrity

Testing 76 - [Black Box] Admin movie create/edit/delete is reflected on customer-facing movie pages.
Testing 77 - [Black Box] Admin user create/edit validates required fields and password rules.
Testing 78 - [Black Box] Admin show/schedule creation blocks invalid datetime and overlap cases.
Testing 79 - [Security/Black Box] Vendor access control and ticket validation (valid QR accepted, invalid/reused QR rejected).
Testing 80 - [E2E Regression] Full critical flow: register -> OTP verify -> login -> book seat -> pay -> download ticket -> verify booking history.
