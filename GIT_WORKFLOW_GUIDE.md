# Git Workflow Guide - Feature-Based Commits
## Professional Development History Setup

---

## Part 1: Improve .gitignore

Your current .gitignore is incomplete. Create a comprehensive one:

**File: `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
ENV/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
pip-wheel-metadata/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST
.pytest_cache/
.coverage
.coverage.*
htmlcov/

# Django
*.log
local_settings.py
db.sqlite3
db.sqlite3-journal
/media
/static
/staticfiles

# IDE
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store
.project
.pydevproject
.settings
*.sublime-project
*.sublime-workspace

# Environment
.env
.env.local
.env.*.local
.env.example

# Node/Frontend
node_modules/
npm-debug.log
yarn-error.log
dist/
.next/
out/
build/

# OS
.DS_Store
Thumbs.db
.bashrc
.bash_history

# Testing
.pytest_cache/
.tox/
coverage.xml

# Temporary
*.tmp
*.bak
temp/
tmp/

# Specific to your project
mediafiles/
staticfiles/
.env.production
secrets.json
*.sqlite

# Keep migrations but ignore pyc
!**/migrations/
**/migrations/__pycache__/
```

---

## Part 2: Feature-Based Commit Strategy

Your project has these logical features:

### Backend Features (Django)
1. **Project Setup** - Settings, URLs, WSGI/ASGI configs
2. **Authentication System** - User, Admin models, OTP, Login views
3. **Catalog/Movies** - Movie models, genres, reviews, cast management
4. **Venue/Shows Management** - Vendor, Shows, Screens, Seats, Pricing
5. **Booking System** - Booking models, Ticket creation, cancellation policy
6. **Finance System** - Wallet, Transactions, Commission system, Withdrawals
7. **Food/Concessions** - Food items, combos, inventory, orders
8. **Promotions/Campaigns** - Coupons, campaigns, promo codes
9. **Notifications** - Email/SMS alerts, notification models
10. **Admin Dashboard** - Admin views, reports, management pages
11. **Vendor Portal** - Vendor views, staff management, analytics
12. **Customer Portal** - Customer pages, profile, booking history
13. **Migrations** - Database schema evolution

### Frontend Features (React/Vue)
1. **UI Setup** - Project structure, routing, layout components
2. **Authentication UI** - Login, register, password reset pages
3. **Customer Pages** - Home, movie listing, movie details, schedules
4. **Booking Flow** - Seat selection, checkout, payment
5. **Payment Integration** - eSewa, Khalti payment gateways
6. **User Dashboard** - Profile, booking history, notifications
7. **Admin Panel** - Dashboard, manage movies, shows, users, reports
8. **Vendor Panel** - Dashboard, manage shows, seats, pricing, staff
9. **Styling & Assets** - CSS, images, responsive design

---

## Part 3: Git Commands - Step by Step

### Step 1: Fix .gitignore First

```bash
cd /path/to/Mero\ Ticket

# Update .gitignore with comprehensive rules (see Part 1)
# Then remove items that should be ignored
git rm --cached db.sqlite3      # Don't track database
git rm --cached backend/media/* # Don't track uploads
git rm -r --cached node_modules # Remove node_modules from tracking

# Add updated .gitignore
git add .gitignore
git commit -m "chore: improve .gitignore for Python and Node projects"
```

### Step 2: Commit Backend Features (Feature by Feature)

#### Commit 1: Backend Setup & Configuration

```bash
# Stage Django settings and configuration
git add backend/backend/settings.py
git add backend/backend/urls.py
git add backend/backend/asgi.py
git add backend/backend/wsgi.py
git add backend/manage.py
git add backend/requirement.txt
git add backend/db_backends/

git commit -m "refactor: modernize Django settings and URL configuration

- Update INSTALLED_APPS for better app organization
- Implement environment-based settings
- Add CORS and security middleware configuration
- Set up DRF and REST framework defaults
- Configure static and media file handling"
```

#### Commit 2: Authentication System

```bash
# Stage all auth-related code
git add backend/app/models.py  # Only User, Admin, OTPVerification, LoginAttempt
git add backend/app/views/auth.py
git add backend/app/views/users.py
git add backend/app/serializers.py  # Auth serializers

git commit -m "feat: implement user authentication system

Features:
- User registration with phone and email validation
- Admin account management and role-based access
- OTP verification for secure phone-based registration
- Login attempt tracking for security
- Password hashing and management
- Custom authentication middleware

Models:
- User (phone, email, profile)
- Admin (role-based permissions)
- OTPVerification (temporary codes)
- LoginAttempt (security tracking)"
```

#### Commit 3: Movie Catalog System

```bash
git add backend/app/models.py  # Movie, MovieGenre, Person, Review, MovieCredit
git add backend/app/views/movies.py
git add backend/app/serializers.py  # Movie serializers

git commit -m "feat: implement movie catalog and content management

Features:
- Browse and search movie catalog
- Movie details with genres, cast, and ratings
- User reviews and ratings for movies
- Content restrictions and parental guidance
- Movie images and promotional content

Models:
- Movie (title, description, rating, genre, cast)
- MovieGenre (category classification)
- Person (actors, directors, crew)
- MovieCredit (cast and crew associations)
- Review (user ratings and feedback)"
```

#### Commit 4: Venue & Show Management

```bash
git add backend/app/models.py  # Vendor, Show, Screen, Seat, SeatCategory, PricingRule, VendorCancellationPolicy
git add backend/app/views/shows.py
git add backend/app/views/seats.py
git add backend/app/views/vendors.py
git add backend/app/serializers.py  # Venue serializers

git commit -m "feat: implement venue and show scheduling system

Features:
- Theater/venue creation and management
- Show scheduling with multiple screens
- Dynamic seat management with categories
- Pricing rules for different seat types and times
- Vendor cancellation policies
- Show status tracking (active, archived, cancelled)

Models:
- Vendor (theater operator details)
- Show (movie schedules with date/time)
- Screen (theater screens/halls)
- Seat (individual seat mapping)
- SeatCategory (premium, standard, economy)
- PricingRule (dynamic pricing)
- VendorCancellationPolicy (refund rules)"
```

#### Commit 5: Booking & Ticket System

```bash
git add backend/app/models.py  # Booking, Ticket, TicketValidationScan
git add backend/app/views/booking.py
git add backend/app/views/bookings.py
git add backend/app/views/ticket_validation.py
git add backend/app/serializers.py  # Booking serializers

git commit -m "feat: implement ticket booking and validation system

Features:
- Multi-seat booking with hold/reserve functionality
- Real-time seat availability tracking
- Ticket generation with QR codes
- Booking cancellation with refund processing
- Ticket validation and scanning
- Booking status tracking (pending, confirmed, cancelled)

Models:
- Booking (order details, payment status)
- Ticket (individual tickets with QR codes)
- TicketValidationScan (scan history and verification)
- BookingDiscount (coupon and discount application)"
```

#### Commit 6: Finance & Wallet System

```bash
git add backend/app/models.py  # Wallet, Transaction, Payment
git add backend/app/views/admin_home.py
git add backend/app/views/coupons.py
git add backend/app/serializers.py  # Finance serializers

git commit -m "feat: implement wallet and payment transaction system

Features:
- Vendor wallet balance tracking
- Transaction history with detailed audit trail
- Commission calculation and distribution
- Platform revenue tracking
- Admin withdrawal request approval/rejection
- Payment status tracking (pending, completed, failed, refunded)
- Commission percentage management (platform + vendor override)
- Automatic earning reversal on refunds

Models:
- Wallet (vendor balance and pending amounts)
- Transaction (comprehensive transaction log)
- Payment (payment method tracking)
- Transaction types: BOOKING, REFUND, COMMISSION, WITHDRAWAL, REVERSAL"
```

#### Commit 7: Promotions & Coupons System

```bash
git add backend/app/models.py  # Coupon, CouponUse, VendorCampaign, VendorCampaignPromoCode
git add backend/app/serializers.py  # Coupon serializers

git commit -m "feat: implement promotions and discount coupon system

Features:
- Coupon management with usage limits
- Promo code generation and validation
- Campaign creation and tracking
- Vendor-specific campaigns and offers
- Usage analytics and redemption tracking
- Discount application on bookings

Models:
- Coupon (promo codes with validity)
- CouponUse (usage tracking and limits)
- VendorCampaign (vendor-specific campaigns)
- VendorCampaignPromoCode (campaign-linked codes)"
```

#### Commit 8: Food & Concessions System

```bash
git add backend/app/models.py  # FoodItem, FoodCombo, FoodInventory, FoodOrder
git add backend/app/views/food.py
git add backend/app/serializers.py  # Food serializers

git commit -m "feat: implement food and concession ordering system

Features:
- Food item catalog with pricing
- Combo meal creation and management
- Inventory tracking per venue
- Food order placement and fulfillment
- Vendor-specific food items
- Add-on ordering with bookings

Models:
- FoodItem (snacks, beverages, meals)
- FoodCombo (bundle deals)
- FoodInventory (stock tracking)
- FoodOrder (order history and status)"
```

#### Commit 9: Notifications System

```bash
git add backend/app/models.py  # Notification
git add backend/app/views/notifications.py
git add backend/app/serializers.py  # Notification serializers

git commit -m "feat: implement notification and alert system

Features:
- Real-time booking confirmation notifications
- Refund and cancellation alerts
- Event reminders (show starting soon)
- Promotional notifications
- Admin system alerts
- Email and SMS notification support

Models:
- Notification (alert content and delivery status)
- Notification types: BOOKING, CANCELLATION, REFUND, REMINDER, PROMO"
```

#### Commit 10: Database Migrations

```bash
git add backend/app/migrations/

git commit -m "chore: add database migrations for all features

Includes schema for:
- User authentication and profiles
- Movie catalog and reviews
- Venue and show management
- Booking and tickets
- Wallet and transactions
- Coupons and campaigns
- Food inventory
- Notifications"
```

#### Commit 11: Admin Panel APIs

```bash
git add backend/app/views/admin_home.py
# Add admin-specific serializers and endpoints

git commit -m "feat: implement admin dashboard APIs

Features:
- Admin user management
- Revenue analytics and reports
- Booking statistics and trends
- Vendor performance tracking
- Payment reconciliation
- System health monitoring
- User activity logs"
```

### Step 3: Commit Frontend Features

#### Commit 12: Frontend Project Setup

```bash
# Frontend setup
git add frontend/package.json
git add frontend/vite.config.js
git add frontend/index.html
git add frontend/src/main.jsx
git add frontend/src/App.jsx
git add frontend/src/index.css

git commit -m "chore: initialize React frontend with Vite

Setup:
- Vite configuration for optimized builds
- ESLint and code quality tools
- React Router for navigation
- Context API for state management
- Responsive design with CSS Grid/Flexbox"
```

#### Commit 13: Authentication UI

```bash
git add frontend/src/pages/Login.jsx
git add frontend/src/pages/Profile.jsx
git add frontend/src/lib/authSession.js
git add frontend/src/context/Appcontext.jsx

git commit -m "feat: implement user authentication pages

Features:
- User registration form with validation
- Admin login interface
- Vendor portal login
- Password reset flow
- Session management
- Token-based authentication"
```

#### Commit 14: Customer Portal - Movies & Catalog

```bash
git add frontend/src/pages/Home.jsx
git add frontend/src/pages/Movies.jsx
git add frontend/src/pages/MovieDetails.jsx
git add frontend/src/components/NowShowingCard.jsx
git add frontend/src/components/HeroSlider.jsx
git add frontend/src/css/home.css
git add frontend/src/css/movieDetails.css

git commit -m "feat: implement customer home and movie catalog

Features:
- Homepage with featured movies slider
- Movie catalog with search and filter
- Movie details page with ratings and reviews
- Responsive hero section
- Promotional banners
- Featured content display

Components:
- HeroSlider (movie carousel)
- NowShowingCard (movie grid)
- MovieDetails (full information)"
```

#### Commit 15: Booking Flow - Shows & Schedules

```bash
git add frontend/src/pages/Schedules.jsx
git add frontend/src/pages/MovieSchedule.jsx
git add frontend/src/pages/SeatSelection.jsx
git add frontend/src/css/schedule.css
git add frontend/src/css/seatSelection.css

git commit -m "feat: implement show scheduling and seat selection

Features:
- Show schedule browser by date and venue
- Seat map visualization
- Real-time seat availability
- Interactive seat selection
- Booking summary before checkout
- Price breakdown display"
```

#### Commit 16: Payment Integration

```bash
git add frontend/src/pages/OrderConfirm.jsx
git add frontend/src/pages/PaymentSuccess.jsx
git add frontend/src/pages/PaymentFailure.jsx
git add frontend/src/pages/EsewaCheckout.jsx

git commit -m "feat: implement payment gateway integration

Gateways:
- eSewa payment integration with QR
- Khalti payment processing
- Payment success/failure handling
- Order confirmation page
- Receipt generation

Features:
- Secure payment processing
- Transaction tracking
- Error handling and retry logic
- Payment status notifications"
```

#### Commit 17: Customer Dashboard

```bash
git add frontend/src/pages/BookingHistory.jsx
git add frontend/src/pages/Notifications.jsx
git add frontend/src/pages/FoodBeverage.jsx
git add frontend/src/css/customerPages.css

git commit -m "feat: implement customer user dashboard

Features:
- Booking history and ticket details
- Active and past bookings
- Notification inbox
- Food ordering interface
- User profile management
- Download and share tickets"
```

#### Commit 18: Admin Dashboard

```bash
git add frontend/src/admin/AdminDashboard.jsx
git add frontend/src/admin/AdminLayout.jsx
git add frontend/src/admin/AdminSidebar.jsx
git add frontend/src/admin/AdminTopbar.jsx
git add frontend/src/admin/AdminMovies.jsx
git add frontend/src/admin/AdminShows.jsx
git add frontend/src/admin/AdminUsers.jsx
git add frontend/src/admin/AdminBookings.jsx
git add frontend/src/admin/AdminVendors.jsx
git add frontend/src/admin/AdminReports.jsx
git add frontend/src/admin/AdminBanners.jsx
git add frontend/src/admin/AdminPeople.jsx
git add frontend/src/admin/AdminCoupons.jsx
git add frontend/src/admin/AdminTrailers.jsx
git add frontend/src/admin/components/MovieForm.jsx
git add frontend/src/css/admin.css

git commit -m "feat: implement comprehensive admin management panel

Features:
- Admin dashboard with analytics
- Movie and show management
- User management and moderation
- Booking overview and support
- Vendor account management
- Revenue reports and analytics
- Coupon and campaign management
- Content moderation (banners, trailers)
- Bulk operations support

Components:
- AdminMovies (CRUD operations)
- AdminShows (schedule management)
- AdminUsers (user accounts)
- AdminBookings (order management)
- AdminVendors (vendor oversight)
- AdminReports (analytics)"
```

#### Commit 19: Vendor Portal

```bash
git add frontend/src/vendor/VendorDashboard.jsx
git add frontend/src/vendor/VendorLayout.jsx
git add frontend/src/vendor/VendorSidebar.jsx
git add frontend/src/vendor/VendorTopbar.jsx
git add frontend/src/vendor/VendorShows.jsx
git add frontend/src/vendor/VendorSeats.jsx
git add frontend/src/vendor/VendorProfile.jsx
git add frontend/src/vendor/VendorBookings.jsx
git add frontend/src/vendor/VendorTicketValidation.jsx
git add frontend/src/vendor/VendorFoodItems.jsx
git add frontend/src/vendor/VendorPricingRules.jsx
git add frontend/src/vendor/VendorStaffAccounts.jsx
git add frontend/src/vendor/VendorCampaignPromos.jsx
git add frontend/src/vendor/VendorCorporateBulkBookings.jsx
git add frontend/src/css/vendor.css

git commit -m "feat: implement vendor management portal

Features:
- Vendor dashboard with analytics
- Show and schedule management
- Seat pricing and configuration
- Booking and revenue tracking
- Ticket validation and scanning
- Food item and inventory management
- Pricing rule configuration
- Staff account management
- Campaign and promo code creation
- Corporate bulk booking handling
- Performance analytics

Components:
- VendorShows (schedule management)
- VendorSeats (seat configuration)
- VendorPricingRules (dynamic pricing)
- VendorTicketValidation (QR scanning)
- VendorCampaignPromos (offer management)
- VendorStaffAccounts (team management)"
```

#### Commit 20: API Integration & Utils

```bash
git add frontend/src/api/api.js
git add frontend/src/lib/catalogApi.js
git add frontend/src/lib/showUtils.js
git add frontend/src/components/Layout.jsx
git add frontend/src/components/Header.jsx

git commit -m "feat: implement API client and utility functions

Features:
- Centralized API communication layer
- Authentication token management
- Error handling and retry logic
- Request/response interceptors
- Catalog API helper functions
- Show scheduling utilities
- Common layout components

Utilities:
- API client with Axios
- Token refresh handling
- Error normalization
- Request logging
- Common component layouts"
```

#### Commit 21: Additional Assets & Components

```bash
git add frontend/src/components/AdultWarningModal.jsx
git add frontend/src/assets/not-found.png
git add frontend/src/pages/NotFound.jsx
git add frontend/src/css/adultWarning.css
git add frontend/src/css/not-found.css
git add frontend/src/css/

git commit -m "feat: add utility components and styling

Components:
- Adult content warning modal
- 404 Not Found page
- Error boundary components

Styling:
- Complete CSS styling for all pages
- Responsive design system
- Theme and color variables
- Animation and transition effects
- Mobile-first approach"
```

### Step 4: Complete Commit List

```bash
# Do all commits in this order:
git commit -m "chore: improve .gitignore"
git commit -m "refactor: modernize Django settings"
git commit -m "feat: implement authentication system"
git commit -m "feat: implement movie catalog"
git commit -m "feat: implement venue and shows"
git commit -m "feat: implement booking system"
git commit -m "feat: implement finance and wallet"
git commit -m "feat: implement promotions system"
git commit -m "feat: implement food system"
git commit -m "feat: implement notifications"
git commit -m "chore: add database migrations"
git commit -m "feat: implement admin panel"
git commit -m "chore: initialize frontend"
git commit -m "feat: implement auth UI"
git commit -m "feat: implement movie catalog UI"
git commit -m "feat: implement booking flow"
git commit -m "feat: implement payment integration"
git commit -m "feat: implement customer dashboard"
git commit -m "feat: implement admin dashboard"
git commit -m "feat: implement vendor portal"
git commit -m "feat: implement API integration"
git commit -m "feat: add utilities and styling"
git commit -m "docs: add project documentation"
```

---

## Part 4: Commit Message Format (Conventional Commits)

### Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types
- **feat**: A new feature
- **fix**: A bug fix
- **refactor**: Code change without feature or bug fix
- **chore**: Dependency updates, .gitignore, configuration
- **docs**: Documentation changes
- **style**: Code style without logic change
- **perf**: Performance improvements
- **test**: Test additions/modifications

### Scope Examples
- auth
- catalog
- venues
- bookings
- finance
- food
- admin
- vendor
- frontend
- backend

### Subject Rules
- Use imperative mood ("implement" not "implemented")
- Don't capitalize first letter
- No period at end
- Max 50 characters

### Body Tips
- Wrap at 72 characters
- Explain *what* and *why*, not *how*
- Use bullet points for features
- Reference issues: "Fixes #123"

### Examples

**Bad:**
```
Updated stuff
Fixed database
Admin page done
```

**Good:**
```
feat(auth): implement user registration with OTP verification

- Add phone-based registration flow
- Implement OTP generation and validation
- Add password hashing with bcrypt
- Create login attempt tracking for security

Fixes #45
```

---

## Part 5: Push to GitHub

```bash
# View remote
git remote -v

# If no remote, add it
git remote add origin https://github.com/yourusername/mero-ticket.git

# Push all local commits
git push origin main

# Or force push (use carefully!)
git push origin main --force

# Verify it worked
git log --oneline -5  # Should show last 5 commits
```

---

## Part 6: Interactive Rebase (If Squashing Needed)

If you committed but want to reorganize:

```bash
# Show last 20 commits for interactive editing
git rebase -i HEAD~20

# In the editor:
# pick = keep commit
# squash = combine with previous
# reword = change commit message
# drop = remove commit

# After done:
git push origin main --force-with-lease
```

---

## Part 7: Viewing History

```bash
# One-line log
git log --oneline

# Pretty graph
git log --oneline --graph --all --decorate

# By author
git log --oneline --author="Ashim"

# Since date
git log --oneline --since="2 weeks ago"

# Changed files
git log --name-status --oneline

# Statistics
git log --stat --oneline
```

---

## Quick Reference - Ready-to-Use Commands

### Commit A Feature
```bash
# Stage files for a feature
git add <file1> <file2> <file3>

# Commit with proper message
git commit -m "feat(scope): implement feature description

- Feature detail 1
- Feature detail 2
- Feature detail 3"

# Or without details
git commit -m "feat(scope): implement feature description"
```

### Push All Commits
```bash
git push origin main
```

### Undo Last Commit (Keep Changes)
```bash
git reset --soft HEAD~1
```

### Redo Commit Message
```bash
git commit --amend -m "new message"
```

### See What Changed
```bash
git diff HEAD~1  # Compare with previous commit
```

---

## After You Commit All Features

Your repository structure should look like:
```
commit 1: chore: improve .gitignore
commit 2: refactor: modernize Django settings  
commit 3: feat(auth): implement authentication
commit 4: feat(catalog): implement movie catalog
...
commit 23: docs: add README and documentation
```

When viewed on GitHub, each commit shows:
- ✅ What files changed
- ✅ What was added/removed
- ✅ Feature description
- ✅ Clear development progression

This looks like a well-organized development project! 🎉

