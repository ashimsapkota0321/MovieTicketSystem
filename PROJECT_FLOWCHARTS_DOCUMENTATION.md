## Latest Features Added

1. **Camera Option for Ticket Scanning**
  - Allows entry validation using device camera to scan tickets.

2. **QR Code Fallback for Ticket Validation**
  - Provides an alternative QR code scanning method if camera scanning fails.

3. **Real-time Notifications for Ticket Scan and Entry Status**
  - Instantly notifies users and staff about scan results and entry status.

4. **Commission Calculation for Admin on Successful Bookings**
  - Automatically calculates and displays admin commission for each booking.

5. **Downloadable Transaction and Earnings Reports**
  - Enables CSV export of transaction and earnings data for Admin and Vendor dashboards.

6. **Enhanced Vendor Analytics Dashboard**
  - New charts, filters, and metrics for vendors to analyze sales and performance.

7. **Refund and Cancellation Request Interface**
  - UI for users to request refunds or cancellations, with backend processing.

8. **Camera Scan Logs for Audit and Security**
  - Stores logs of all camera-based scans for security and audit purposes.

9. **Export and Print Options for Scan Logs**
  - Allows exporting and printing of scan logs for record-keeping.

10. **Improved Email Notification System**
   - Enhanced reliability and formatting of email notifications for booking, payment, and status updates.

11. **Email Debugging Toolkit**
   - Tools and documentation for testing and troubleshooting email delivery and formatting issues.

12. **Automatic Booking and Payment Status Updates**
   - System automatically updates booking and payment statuses based on transaction results.

13. **Transaction History with Filtering**
   - Admin and Vendor dashboards now support advanced filtering of transaction history.
---

Logbook: 15  
Meeting No: 15   Date: 2026/03/30  
Start Time: 08:30 AM   End Time: 09:00 AM  
Items Discussed:  
• Demonstrated commission calculation for Admin on successful bookings.  
• Showed new camera-based ticket scanning feature for entry validation.  
• Reviewed downloadable transaction and earnings reports for Admin dashboard.  
• Discussed improvements to vendor-side analytics and reporting.  
• Explored user feedback on payment and booking flow.  
Achievements:  
• Integrated camera option for ticket scanning at entry points.  
• Enabled commission calculation and display in Admin dashboard.  
• Added downloadable CSV reports for transactions and earnings.  
• Improved vendor analytics with new charts and filters.  
Problems:  
• Minor issues with camera permissions on some devices, workaround identified.  
• Need to enhance error handling for failed ticket scans.  
Tasks for the Next Meeting:  
• Implement QR code fallback for ticket validation.  
• Add real-time notifications for scan results and entry status.  
• Refine vendor analytics dashboard based on feedback.  
• Begin work on refund and cancellation request UI.  
…………………   …………….…………………  
Asim Sapkota   Sandesh Hamal Thakuri  
(1st Supervisor)

---

Logbook: 16  
Meeting No: 16   Date: 2026/04/06  
Start Time: 08:30 AM   End Time: 09:00 AM  
Items Discussed:  
• Demonstrated QR code fallback for ticket validation.  
• Showed real-time notifications for ticket scan and entry status.  
• Reviewed updated vendor analytics dashboard with new metrics.  
• Presented initial refund and cancellation request UI.  
• Discussed integration of camera scan logs for audit purposes.  
Achievements:  
• Successfully implemented QR code fallback for ticket scanning.  
• Enabled real-time notifications for entry validation events.  
• Enhanced vendor analytics with additional metrics and export options.  
• Developed and tested refund/cancellation request interface.  
• Integrated camera scan logs for security and audit tracking.  
Problems:  
• Occasional delay in real-time notification delivery, optimization planned.  
• Some users reported confusion with new refund UI, further UX review needed.  
Tasks for the Next Meeting:  
• Optimize notification delivery for ticket scan events.  
• Conduct user testing on refund/cancellation UI and iterate design.  
• Add export and print options for scan logs.  
• Plan for final round of system integration testing.  
…………………   …………….…………………  
Asim Sapkota   Sandesh Hamal Thakuri  
(1st Supervisor)
## Activity Diagram: User Registration

```mermaid
flowchart TD
  %% Swimlanes
  subgraph Customer
    A([Initial Node])
    B[Fill Registration Form]
    C[Submit Form]
    D{Retry?}
    E[See Success Message]
    F[Cancel Registration]
    G([Activity Final Node])
  end

  subgraph System
    H[Validate Form Data]
    I{Data Valid?}
    J[Create User Account]
    K[Send Confirmation Email]
    L[Show Error Message]
    M((Merge Node))
    N[[Fork Node]]
    O[Log Registration]
    P[Send Welcome Notification]
    Q((Join Node))
  end

  %% Flow
  A --> B
  B --> C
  C --> H
  H --> I
  I -- Yes --> N
  I -- No --> L
  L --> D
  D -- Yes --> B
  D -- No --> F
  F --> G
  N --> J
  N --> O
  J --> K
  K --> M
  O --> P
  P --> Q
  M --> Q
  Q --> E
  E --> G
```

**Notations Used:**
- **Initial Node**: Start of the process
- **Activity State**: Actions like filling form, validation, etc.
- **Control Flow**: Arrows between actions
- **Decision Node**: “Data Valid?” and “Retry?” for branching
- **Merge Node**: Merges flows after confirmation email and parallel logging
- **Fork Node**: Splits into “Create User Account” and “Log Registration” in parallel
- **Join Node**: Joins parallel flows before showing success
- **Activity Final Node**: End of the process

# Mero Ticket Project - Comprehensive Flowchart Documentation

## Overview
This document contains 15 detailed flowcharts covering all major business processes and workflows in the Mero Ticket application. These flowcharts serve as the final report documentation for the project.

---

## 1. User Registration and OTP Verification Flow

**Purpose**: Documents the entire user signup process from phone number validation through OTP verification and account creation.

**Key Components**:
- Phone number uniqueness validation
- OTP generation and delivery (SMS/Email)
- OTP verification with expiry handling
- User account creation
- Referral code generation
- Signup metadata tracking (IP, User Agent, Device Fingerprint)

**Status Outcomes**: Registration Complete or Error

---

## 2. Ticket Booking Flow

**Purpose**: Covers the complete ticket booking process from show selection to booking confirmation.

**Key Components**:
- Movie and show selection
- Seating layout visualization
- Seat availability check
- 30-minute seat lock mechanism
- Price calculation with pricing rules
- Coupon/discount application
- Payment processing
- Ticket generation and confirmation

**Status Outcomes**: Booking Complete or Booking Failed

---

## 3. Payment Processing and Verification

**Purpose**: Handles payment gateway integration, transaction verification, and payment status management.

**Key Components**:
- Transaction ID generation
- Payment record creation (PENDING status)
- Gateway communication
- Server-side transaction verification
- Manual review for mismatches
- Wallet balance updates
- Booking record finalization

**Status Outcomes**: Payment Success, Failed, or Manual Review Required

---

## 4. Ticket Validation and Scanning

**Purpose**: Manages venue check-in process, ticket validation, and attendance tracking.

**Key Components**:
- QR code/Ticket ID scanning
- Ticket details retrieval
- Booking status verification
- Show time validation
- Duplicate entry prevention
- Validation record creation
- Attendance tracking

**Status Outcomes**: Entry Granted or Entry Denied

---

## 5. Refund Processing

**Purpose**: Manages refund requests with cancellation policy enforcement.

**Key Components**:
- Cancellation policy window check
- Show status verification
- Refund amount calculation
- Cancellation charge application
- Booking status update (CANCELLED)
- Seat release to pool
- Original payment method refund
- Refund ledger entry creation

**Status Outcomes**: Refund Approved, Denied, or Pending

---

## 6. Wallet and Transaction Management

**Purpose**: Manages user wallet operations and transaction ledger.

**Key Components**:
- Transaction type routing (Credit, Debit, Referral, Loyalty)
- Wallet balance updates
- Immutable ledger entry creation
- Transaction status validation
- Notification queueing
- Balance reconciliation

**Status Outcomes**: Transaction Complete or Rejected

---

## 7. Food Ordering Flow

**Purpose**: Handles food item selection and ordering integrated with ticket booking.

**Key Components**:
- Food menu browsing
- Item selection and cart management
- Food price calculation
- Discount application
- Tax calculation
- Order confirmation
- Kitchen system integration
- User notification

**Status Outcomes**: Order Success or Order Failed

---

## 8. Vendor Onboarding and Activation

**Purpose**: Complete vendor registration and activation process.

**Key Components**:
- Application submission with business details
- Document upload (KYC, Bank Info)
- Admin application review
- Commission rate setting
- Vendor wallet creation
- Profile activation
- Hall and Screen setup
- Movie and show management activation

**Status Outcomes**: Vendor Activated or Application Rejected

---

## 9. Vendor Payout and Withdrawal Process

**Purpose**: Manages vendor earnings withdrawal with compliance checks.

**Key Components**:
- Minimum balance verification
- Bank account validation
- Withdrawal amount calculation with fees
- Admin manual review for fraud detection
- Bank transfer initiation
- Settlement tracking (2-5 business days)
- Transfer verification
- Wallet debit confirmation
- User notification

**Status Outcomes**: Withdrawal Completed, Rejected, or Failed

---

## 10. Admin Dashboard and Control Panel

**Purpose**: Overview of admin functions and system management capabilities.

**Key Components**:
- Movie and show management
- Pricing rule configuration
- Commission and revenue settings
- Dashboard analytics and reporting
- Booking and revenue monitoring
- User and admin management
- Refund request processing
- Vendor and staff management
- Payment and transaction monitoring
- Loyalty and rewards management
- Audit logging and reporting

**Status Outcomes**: System Configured and Monitored

---

## 11. Referral System and Rewards

**Purpose**: Manages user referral program with fraud prevention.

**Key Components**:
- Referral code generation and sharing
- Code validation and self-referral detection
- Friend signup verification
- Welcome bonus creation
- 7-day hold period enforcement
- Spending threshold validation
- Reward release to both users
- Wallet transaction creation
- User notification

**Status Outcomes**: Referral Completed or Cancelled

---

## 12. Notification System

**Purpose**: Handles all system notifications via multiple channels.

**Key Components**:
- Event-triggered notifications
  - Booking confirmation
  - Payment receipt
  - Refund confirmation
  - Pre-show reminders
  - Loyalty points credit
- Channel selection (SMS, Email, Push)
- Message queuing
- Delivery with retry logic
- Status tracking and logging

**Status Outcomes**: Notification Sent or Delivery Failed

---

## 13. Loyalty Program and Rewards Redemption

**Purpose**: Manages loyalty points earning and redemption.

**Key Components**:
- Points calculation based on spend
- User tier checking (Silver/Gold/Platinum)
- Tier multiplier application
- Loyalty transaction creation
- Active promotion checking
- Bonus points application
- Reward selection and validation
- Points deduction
- Redemption record creation
- Reward delivery

**Status Outcomes**: Points Credited or Reward Redeemed

---

## 14. Movie & Show Management

**Purpose**: Complete movie and show creation workflow.

**Key Components**:
- Movie details input (Title, Genre, Rating)
- Poster and cast photos upload
- Cast and crew information
- Content rating assignment
- Description and review management
- Show creation from movies
- Venue and screen assignment
- Seating layout configuration
- Base pricing setup
- Dynamic pricing rules
- Commission configuration
- Publication and activation
- Promotion management

**Status Outcomes**: Show Published or Draft Saved

---

## 15. Role-Based Access Control (RBAC)

**Purpose**: Enforces authorization and access control across the system.

**Key Components**:
- JWT token extraction and validation
- Token signature and expiry verification
- User role fetching from database
- Role-specific permission checking
  - **User**: Own booking access, public data
  - **Admin**: Dashboard, user management, configuration
  - **Vendor**: Own show management, wallet access
- Resource ownership verification
- Access grant or denial
- Audit logging
- Error responses (401 Unauthorized, 403 Forbidden)

**Status Outcomes**: Access Granted or Access Denied

---

## Data Models Involved

The flowcharts reference the following key models:
- **User**: Users, Admin, Vendor, VendorStaff
- **Content**: Movie, Person, MovieCredit, Show, Screen, Seat
- **Booking**: Booking, BookingSeat, Ticket, TicketValidationScan
- **Payment**: Payment, Transaction, Refund
- **Wallet**: Wallet, UserWallet, AdminWallet, ReferralWallet, UserLoyaltyWallet
- **Ledger**: VendorCommissionLedger, RefundLedger, ReversalLedger, WithdrawalLedger
- **Loyalty**: LoyaltyProgramConfig, LoyaltyTransaction, Reward, RewardRedemption
- **Notification**: Notification
- **Food**: FoodItem, BookingFoodItem

---

## System Architecture Layers

### Frontend (React/Vite)
- User Interface for all customer-facing flows
- Admin dashboard for management functions
- Vendor portal for show and inventory management

### Backend (Django)
- API endpoints for all flows
- Business logic and validation
- Database transaction management
- Payment gateway integration

### Database
- Relational data models
- Ledger-based financial tracking
- Queue tables for background jobs

### External Integrations
- Payment Gateway (Payment verification)
- SMS/Email Gateway (OTP, Notifications)
- Banking APIs (Vendor payouts)

---

## Critical Business Rules Enforced

1. **Payment Verification**: Server-side validation before booking finalization
2. **Seat Locking**: 30-minute hold with automatic release
3. **Cancellation Policy**: Time-based and status-based refund rules
4. **Referral Fraud Prevention**: Self-referral detection, device fingerprinting, spending thresholds
5. **Wallet Ledger**: Immutable transaction history for financial audits
6. **Role-Based Access**: JWT-based authentication with granular permissions
7. **Vendor Compliance**: KYC, bank verification, manual review for withdrawals
8. **Loyalty Tiers**: Dynamic point multipliers based on user tier
9. **Notification Retries**: Exponential backoff for failed deliveries
10. **Audit Logging**: All critical operations logged for compliance

---

## Future Enhancement Opportunities

Based on the FEATURES_CORRECTIONS_IMPROVEMENTS.md document:

1. **Settlement Lifecycle**: Vendor payout schedules and reconciliation jobs
2. **Chargeback Handling**: Dispute management workflow
3. **Advanced Fraud Detection**: Machine learning for risky booking detection
4. **Audit Trails**: Enhanced logging for admin configuration changes
5. **Dynamic Pricing**: Rule simulation and explainability
6. **Subscription Plans**: Renewal reminders and compatibility checks
7. **Corporate Bookings**: Bulk seat holds and organization-level billing
8. **Vendor Analytics**: Revenue dashboards and performance metrics
9. **Performance Optimization**: Redis caching for aggregates and background jobs
10. **Security Enhancements**: Short-lived tokens, refresh token rotation, rate limiting

---

## Document Version

- **Created**: April 2026
- **Total Flowcharts**: 15
- **Project**: Mero Ticket - Final Report Documentation

---

## How to Use This Documentation

1. **For Development**: Use flowcharts as reference during feature development
2. **For Testing**: Map test cases to flowchart decision points
3. **For Onboarding**: Help new team members understand system processes
4. **For Stakeholders**: Provide visual representation of business logic
5. **For Architecture Review**: Identify bottlenecks and optimization opportunities

---

## Collaboration Diagrams

The diagrams below use collaboration (communication) format: participant/object nodes with numbered message links, aligned to the provided use case model.

### 1. Collaboration Diagram - Register Account

```plantuml
@startuml
title Collaboration Diagram - Register Account
left to right direction
skinparam linetype polyline

actor Guest as G
rectangle ":RegistrationUI" as UI
rectangle ":AuthService" as AUTH
rectangle ":User" as U
rectangle ":OTPVerification" as OTP
rectangle ":NotificationService" as NS

G - UI
UI - AUTH
AUTH - U
AUTH - OTP
AUTH - NS

G -> UI : 1 registerAccount()
UI -> AUTH : 1.1 submitRegistration()
AUTH -> U : 1.1.1 createPendingUser()
AUTH -> OTP : 1.1.2 generateOtp()
AUTH -> NS : 1.1.3 sendOtpNotification()
NS -> G : 1.1.4 deliverOtp()
G -> UI : 2 submitOtp()
UI -> AUTH : 2.1 verifyOtp()
AUTH -> OTP : 2.1.1 validateOtp()
AUTH -> U : 2.1.2 activateUser()
AUTH -> UI : 2.1.3 showRegistrationSuccess()
@enduml
```

### 2. Collaboration Diagram - Browse Movies & Shows

```plantuml
@startuml
title Collaboration Diagram - Browse Movies & Shows
left to right direction
skinparam linetype polyline

actor Guest as G
rectangle ":BrowseUI" as UI
rectangle ":CatalogService" as CAT
rectangle ":Movie" as M
rectangle ":Showtime" as S

G - UI
UI - CAT
CAT - M
CAT - S

G -> UI : 1 browseMovies()
UI -> CAT : 1.1 requestMovies()
CAT -> M : 1.1.1 getAvailableMovies()
CAT -> UI : 1.1.2 displayMovieList()
G -> UI : 2 selectMovie()
UI -> CAT : 2.1 requestMovieDetails()
CAT -> M : 2.1.1 getMovieDetails()
CAT -> S : 2.1.2 getShowtimesForMovie()
CAT -> UI : 2.1.3 displayMovieAndShowtimes()
@enduml
```

### 3. Collaboration Diagram - Book Ticket

```plantuml
@startuml
title Collaboration Diagram - Book Ticket
left to right direction
skinparam linetype polyline

actor Customer as C
rectangle ":BookTicketUI" as UI
rectangle ":BookTicketService" as BT
rectangle ":Movie" as M
rectangle ":Showtime" as ST
rectangle ":Seat" as SE
rectangle ":Booking" as B
rectangle ":PaymentGateway" as PG
rectangle ":NotificationService" as NS

C - UI
UI - BT
BT - M
BT - ST
BT - SE
BT - B
BT - PG
BT - NS

C -> UI : 1 browseMovie()
UI -> BT : 1.1 sendBrowseRequest()
BT -> M : 1.1.1 getAvailableMovies()
BT -> UI : 1.1.2 displayMovies()

C -> UI : 2 selectMovie()
UI -> BT : 2.1 sendMovieDetailsRequest()
BT -> ST : 2.1.1 getShowtimeList()
BT -> UI : 2.1.2 displayShowtimes()

C -> UI : 3 selectShowtime()
UI -> BT : 3.1 sendShowtimeRequest()
BT -> SE : 3.1.1 getAvailableSeats()
BT -> UI : 3.1.2 showSeatMap()

C -> UI : 4 selectSeat()
UI -> BT : 4.1 reserveSeat()
BT -> SE : 4.1.1 lockSeat()
BT -> UI : 4.1.2 showPaymentMethods()

C -> UI : 5 confirmBooking()
UI -> BT : 5.1 createBookingRequest()
BT -> B : 5.1.1 createBooking()
BT -> PG : 5.1.2 initiatePayment()
PG -> BT : 5.1.3 paymentSuccess()
BT -> NS : 5.1.4 sendConfirmation()
BT -> UI : 5.1.5 displayTicket()
@enduml
```

### 4. Collaboration Diagram - Cancel Booking / Process Refund

```plantuml
@startuml
title Collaboration Diagram - Cancel Booking / Process Refund
left to right direction
skinparam linetype polyline

actor Customer as C
rectangle ":BookingHistoryUI" as UI
rectangle ":RefundService" as RF
rectangle ":Booking" as B
rectangle ":Seat" as S
rectangle ":Refund" as R
rectangle ":PaymentGateway" as PG
rectangle ":NotificationService" as NS

C - UI
UI - RF
RF - B
RF - S
RF - R
RF - PG
RF - NS

C -> UI : 1 openBookingHistory()
UI -> RF : 1.1 requestBookings()
RF -> B : 1.1.1 getUserBookings()
RF -> UI : 1.1.2 showBookings()

C -> UI : 2 cancelBooking()
UI -> RF : 2.1 submitCancellation()
RF -> B : 2.1.1 markBookingCancelled()
RF -> S : 2.1.2 releaseSeats()
RF -> R : 2.1.3 createRefundEntry()
RF -> PG : 2.1.4 processRefund()
PG -> RF : 2.1.5 refundCompleted()
RF -> NS : 2.1.6 sendRefundNotification()
RF -> UI : 2.1.7 showCancellationSuccess()
@enduml
```

### 5. Collaboration Diagram - Manage Shows & Schedule

```plantuml
@startuml
title Collaboration Diagram - Manage Shows & Schedule
left to right direction
skinparam linetype polyline

actor Vendor as V
rectangle ":VendorDashboardUI" as UI
rectangle ":ShowManagementService" as SM
rectangle ":Movie" as M
rectangle ":Screen" as SC
rectangle ":Seat" as SE
rectangle ":Showtime" as ST

V - UI
UI - SM
SM - M
SM - SC
SM - SE
SM - ST

V -> UI : 1 openShowManagement()
UI -> SM : 1.1 createShowRequest()
SM -> M : 1.1.1 fetchMovie()
SM -> SC : 1.1.2 validateScreen()
SM -> SE : 1.1.3 validateSeatLayout()
SM -> ST : 1.1.4 saveShowtime()
SM -> UI : 1.1.5 showSavedConfirmation()

V -> UI : 2 updateSchedule()
UI -> SM : 2.1 updateShowtime()
SM -> ST : 2.1.1 modifySchedule()
SM -> UI : 2.1.2 showUpdatedConfirmation()
@enduml
```

### 6. Collaboration Diagram - Food Ordering Flow

```plantuml
@startuml
title Collaboration Diagram - Food Ordering Flow
left to right direction
skinparam linetype polyline

actor Customer as C
rectangle ":FoodMenuUI" as UI
rectangle ":FoodOrderService" as FO
rectangle ":FoodItem" as F
rectangle ":BookingFoodItem" as BFI
rectangle ":CouponService" as CP
rectangle ":PaymentGateway" as PG
rectangle ":KitchenService" as K
rectangle ":NotificationService" as NS

C - UI
UI - FO
FO - F
FO - BFI
FO - CP
FO - PG
FO - K
FO - NS

C -> UI : 1 browseFoodMenu()
UI -> FO : 1.1 requestFoodMenu()
FO -> F : 1.1.1 getAvailableFoodItems()
FO -> UI : 1.1.2 displayFoodMenu()

C -> UI : 2 addFoodToCart()
UI -> FO : 2.1 addItemToCart()
FO -> BFI : 2.1.1 createCartLine()
FO -> UI : 2.1.2 updateCartView()

C -> UI : 3 applyDiscount()
UI -> FO : 3.1 validateCoupon()
FO -> CP : 3.1.1 checkCouponRules()
CP -> FO : 3.1.2 couponApproved()
FO -> UI : 3.1.3 showDiscountedTotal()

C -> UI : 4 confirmFoodOrder()
UI -> FO : 4.1 placeFoodOrder()
FO -> BFI : 4.1.1 saveFoodOrder()
FO -> PG : 4.1.2 initiateFoodPayment()
PG -> FO : 4.1.3 paymentSuccess()
FO -> K : 4.1.4 sendKitchenOrder()
FO -> NS : 4.1.5 notifyCustomerOrderPlaced()
FO -> UI : 4.1.6 showOrderConfirmation()
@enduml
```

### 7. Collaboration Diagram - Vendor Payout and Withdrawal Process

```plantuml
@startuml
title Collaboration Diagram - Vendor Payout and Withdrawal Process
left to right direction
skinparam linetype polyline

actor Vendor as V
rectangle ":VendorWalletUI" as UI
rectangle ":WithdrawalService" as WS
rectangle ":Wallet" as W
rectangle ":WithdrawalLedger" as WL
rectangle ":BankAccountValidator" as BV
rectangle ":AdminReviewQueue" as AR
rectangle ":BankTransferGateway" as BG
rectangle ":NotificationService" as NS

V - UI
UI - WS
WS - W
WS - WL
WS - BV
WS - AR
WS - BG
WS - NS

V -> UI : 1 openWithdrawalPage()
UI -> WS : 1.1 requestWalletSummary()
WS -> W : 1.1.1 getAvailableBalance()
WS -> WL : 1.1.2 getWithdrawalHistory()
WS -> UI : 1.1.3 displayBalanceAndHistory()

V -> UI : 2 submitWithdrawalRequest()
UI -> WS : 2.1 createWithdrawalRequest()
WS -> BV : 2.1.1 validateBankDetails()
BV -> WS : 2.1.2 bankDetailsValid()
WS -> W : 2.1.3 verifyMinimumBalance()
WS -> WL : 2.1.4 createPendingWithdrawal()
WS -> AR : 2.1.5 queueForManualReview()

AR -> WS : 3.1 approveWithdrawal()
WS -> BG : 3.1.1 initiateBankTransfer()
BG -> WS : 3.1.2 transferCompleted()
WS -> W : 3.1.3 debitVendorWallet()
WS -> WL : 3.1.4 updateWithdrawalLedger()
WS -> NS : 3.1.5 sendWithdrawalNotification()
WS -> UI : 3.1.6 showWithdrawalStatus()
@enduml
```

---

## Sequence Diagrams

These are true sequence diagrams with lifelines and ordered interactions.

### 1. Sequence Diagram - Login

```plantuml
@startuml
title Sequence Diagram - Login
actor User
participant LoginUI
participant AuthService
database UserDB
participant SessionStore

User -> LoginUI : enterCredentials()
LoginUI -> AuthService : authenticate(credentials)
AuthService -> UserDB : findUserByEmailOrPhone()
UserDB --> AuthService : userRecord
AuthService -> AuthService : verifyPassword()
alt credentials valid
  AuthService -> SessionStore : createSession()
  SessionStore --> AuthService : sessionCreated
  AuthService --> LoginUI : loginSuccess()
else credentials invalid
  AuthService --> LoginUI : loginFailed()
end
@enduml
```

### 2. Sequence Diagram - Forgot/Reset Password

```plantuml
@startuml
title Sequence Diagram - Forgot/Reset Password
actor User
participant ForgotPasswordUI
participant PasswordResetService
database OTPDB
participant NotificationService
database UserDB

User -> ForgotPasswordUI : requestReset()
ForgotPasswordUI -> PasswordResetService : createResetOTP(email)
PasswordResetService -> UserDB : findUser(email)
UserDB --> PasswordResetService : userFound
PasswordResetService -> OTPDB : createOTP()
PasswordResetService -> NotificationService : sendResetOTP()
NotificationService --> User : deliverResetOTP()
User -> ForgotPasswordUI : submitResetOTPAndPassword()
ForgotPasswordUI -> PasswordResetService : verifyAndReset(otp,newPassword)
PasswordResetService -> OTPDB : validateOTP()
OTPDB --> PasswordResetService : otpValid
PasswordResetService -> UserDB : updatePassword()
PasswordResetService --> ForgotPasswordUI : passwordResetSuccess()
@enduml
```

### 3. Sequence Diagram - Search Movies

```plantuml
@startuml
title Sequence Diagram - Search Movies
actor Guest
participant SearchUI
participant SearchService
database MovieDB

Guest -> SearchUI : enterSearchText()
SearchUI -> SearchService : searchMovies(query)
SearchService -> MovieDB : findMoviesByTitleOrGenre(query)
MovieDB --> SearchService : searchResults
SearchService --> SearchUI : displayResults(searchResults)
Guest -> SearchUI : refineSearch()
SearchUI -> SearchService : searchMovies(updatedQuery)
SearchService -> MovieDB : findMoviesByTitleOrGenre(updatedQuery)
MovieDB --> SearchService : refinedResults
SearchService --> SearchUI : updateResults(refinedResults)
@enduml
```

### 4. Sequence Diagram - View Movie Details

```plantuml
@startuml
title Sequence Diagram - View Movie Details
actor Guest
participant MovieDetailsUI
participant MovieService
database MovieDB
database CastDB
database ReviewDB

Guest -> MovieDetailsUI : selectMovie()
MovieDetailsUI -> MovieService : loadMovieDetails(movieId)
MovieService -> MovieDB : getMovie(movieId)
MovieService -> CastDB : getCast(movieId)
MovieService -> ReviewDB : getReviews(movieId)
MovieDB --> MovieService : movieData
CastDB --> MovieService : castData
ReviewDB --> MovieService : reviewData
MovieService --> MovieDetailsUI : displayMovieDetails()
Guest -> MovieDetailsUI : viewTrailers()
MovieDetailsUI -> MovieService : loadTrailerLinks(movieId)
MovieService -> MovieDB : getTrailerLinks(movieId)
MovieService --> MovieDetailsUI : showTrailers()
@enduml
```

### 5. Sequence Diagram - View Notifications

```plantuml
@startuml
title Sequence Diagram - View Notifications
actor Customer
participant NotificationCenterUI
participant NotificationService
database NotificationDB

Customer -> NotificationCenterUI : openNotifications()
NotificationCenterUI -> NotificationService : fetchNotifications(userId)
NotificationService -> NotificationDB : getUnreadNotifications(userId)
NotificationDB --> NotificationService : notificationList
NotificationService --> NotificationCenterUI : displayNotifications(notificationList)
Customer -> NotificationCenterUI : markAsRead(notificationId)
NotificationCenterUI -> NotificationService : updateNotificationStatus(notificationId)
NotificationService -> NotificationDB : markAsRead(notificationId)
NotificationService --> NotificationCenterUI : statusUpdated()
@enduml
```

---

## Activity Diagrams

These are true activity diagrams with decision paths and flow control.

### 1. Activity Diagram - Payment Activity

```plantuml
@startuml
title Payment Activity Diagram
|Customer|
start
:Review booking summary;
:Select proceed;

|System|
:Display payment details and options;

|Customer|
:Choose payment method;

repeat
  :Enter payment details;
  :Select confirm;

  |System|
  :Validate payment details;
  :Send request to payment gateway;
  :Receive authorization result;

  if (Payment successful?) then (Yes)
    :Confirm booking;
    :Generate ticket;
    |Customer|
    :See success message;
    :View/Download ticket;
    stop
  else (No)
    |Customer|
    :Show error message;
    :Select retry payment;
  endif
repeat while (Retry?) is (Yes)

:Cancel payment;
stop
@enduml
```

### 2. Activity Diagram - Manage Users and Vendors

```plantuml
@startuml
title Activity Diagram - Manage Users and Vendors
start
:Admin opens user management;
:Search user or vendor;
:Select account type;
if (User selected?) then (Yes)
  :View user profile;
  :Choose action activate/block/edit;
  if (Activate?) then (Yes)
    :Activate account;
  elseif (Block?) then (Yes)
    :Block account;
  else (Edit)
    :Update profile fields;
  endif
else (Vendor selected)
  :View vendor profile;
  :Choose action approve/suspend/edit;
  if (Approve?) then (Yes)
    :Approve vendor;
  elseif (Suspend?) then (Yes)
    :Suspend vendor;
  else (Edit)
    :Update vendor details;
  endif
endif
:Save changes;
stop
@enduml
```

### 3. Activity Diagram - Manage Coupons and Global Pricing Rules

```plantuml
@startuml
title Activity Diagram - Manage Coupons and Global Pricing Rules
start
:Admin opens pricing panel;
:Choose coupon or pricing rule;
if (Coupon management?) then (Yes)
  :Enter coupon code and discount;
  :Set validity period;
  :Validate coupon conflict;
  if (Coupon valid?) then (Yes)
    :Save coupon;
  else (No)
    :Show coupon error;
  endif
else (Pricing rule management)
  :Enter base pricing rules;
  :Set time-based modifiers;
  :Set occupancy modifiers;
  :Validate conflicts;
  if (Rule valid?) then (Yes)
    :Save pricing rule;
  else (No)
    :Show rule error;
  endif
endif
stop
@enduml
```

### 4. Activity Diagram - Manage Referral Controls

```plantuml
@startuml
title Activity Diagram - Manage Referral Controls
start
:Admin opens referral settings;
:Configure welcome bonus;
:Set hold period;
:Set spending threshold;
:Enable fraud checks;
:Review self-referral prevention;
if (Settings valid?) then (Yes)
  :Save referral controls;
  :Activate referral program;
else (No)
  :Show validation error;
endif
stop
@enduml
```

### 5. Activity Diagram - Manage Loyalty, Rewards, Promotions

```plantuml
@startuml
title Activity Diagram - Manage Loyalty, Rewards, Promotions
start
:Open loyalty dashboard;
:Check customer tier;
:Calculate point accrual;
:Apply active promotion;
:Select reward for redemption;
if (Enough points?) then (Yes)
  :Deduct points;
  :Create loyalty transaction;
  :Deliver reward;
  :Notify customer;
else (No)
  :Show insufficient points message;
endif
stop
@enduml
```

