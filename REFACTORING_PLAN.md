# Django Multi-App Refactoring Plan
## Ticket System: Complete Architecture Restructuring

**Current State:** Monolithic `app` with 20+ models, 15+ views, single services.py  
**Target State:** Multi-app architecture with clean separation of concerns, scalable structure  
**Risk Level:** Medium (with mitigation via this plan)  
**Timeline Estimate:** 2-3 days implementation + 1 day testing

---

## Phase 0: Pre-Refactoring Checklist

- [ ] Create a new git branch: `git checkout -b refactor/multi-app-architecture`
- [ ] Full database backup
- [ ] Run all tests: `python manage.py test`
- [ ] Document current database version: `python manage.py showmigrations`
- [ ] Ensure no uncommitted changes: `git status`

---

## Phase 1: Architecture Analysis & Planning

### 1.1 Current Domain Mapping

Your models naturally fall into these **business domains**:

```
📦 Backend Project
├── 🔐 Authentication Core
│   ├── User, Admin, OTPVerification, LoginAttempt
│   └── Permissions, Token Management
│
├── 🎬 Catalog Management (Movie Data)
│   ├── Movie, MovieGenre, MovieMovieGenre, MovieCredit
│   ├── Person (actors, directors), Review
│   └── Content metadata (titles, images, ratings)
│
├── 📺 Venue Management (Theater Operations)
│   ├── Show (movie schedule), Screen, Seat, SeatCategory
│   ├── PricingRule, VendorCancellationPolicy
│   └── Vendor, VendorStaff (theater operators)
│
├── 🎫 Booking & Tickets (Customer Transactions)
│   ├── Booking, Ticket, TicketValidationScan
│   ├── Payment, Transaction (finance)
│   └── Seat selection, reservations
│
├── 💳 Finance & Wallet
│   ├── Wallet, Transaction (all types)
│   ├── Coupon, CouponUse, Notification
│   ├── VendorCampaignPromoCode, VendorCampaign
│   └── Withdrawal (admin approval workflows)
│
├── 🍿 Food & Concessions
│   ├── FoodItem, FoodCombo, FoodInventory
│   ├── FoodOrder, FoodOrderItem
│   └── Vendor-specific food inventory
│
├── 📢 Content & Promotions
│   ├── HomeSlide, Banner
│   ├── Collaborator, CollabDetails
│   ├── Push Notifications
│   └── Marketing content
│
└── ⚙️ Shared/Core
    ├── Abstract base classes
    ├── Common utilities
    ├── Middleware, permissions
    └── Settings & configuration
```

### 1.2 Proposed Multi-App Structure

```
backend/
├── manage.py
├── backend/                           # Project settings
│   ├── settings.py                    # Updated INSTALLED_APPS
│   ├── urls.py                        # Root URL config
│   ├── asgi.py
│   └── wsgi.py
│
├── apps/
│   ├── core/                          # Shared utilities & abstract models
│   │   ├── models.py                  # BaseModel, TimestampedModel
│   │   ├── permissions.py             # RoleBasedAccessPermission, AdminRequired
│   │   ├── middleware.py              # Moved from monolithic app
│   │   ├── utils.py                   # Shared functions
│   │   ├── selectors.py               # Shared query helpers
│   │   ├── exceptions.py              # Custom exceptions
│   │   └── migrations/
│   │
│   ├── auth/                          # User authentication & authorization
│   │   ├── models.py                  # User, Admin (no foreign keys to User/Admin models)
│   │   ├── serializers.py             # UserSerializer, AdminSerializer
│   │   ├── viewsets.py                # UserViewSet, AdminViewSet
│   │   ├── services.py                # register_user(), login_user(), reset_password()
│   │   ├── views.py                   # OTP verification, login endpoints
│   │   ├── urls.py
│   │   ├── permissions.py             # Auth-specific permissions
│   │   ├── admin.py
│   │   └── migrations/
│   │
│   ├── catalog/                       # Movie & content metadata
│   │   ├── models.py                  # Movie, MovieGenre, Person, Review, MovieCredit
│   │   ├── serializers.py
│   │   ├── viewsets.py                # MovieViewSet, ReviewViewSet
│   │   ├── services.py                # get_featured_movies(), search_movies()
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── migrations/
│   │
│   ├── venues/                        # Theater/Venue management
│   │   ├── models.py                  # Vendor, VendorStaff, Show, Screen, Seat, SeatCategory, PricingRule
│   │   ├── serializers.py
│   │   ├── viewsets.py                # VendorViewSet, ShowViewSet, SeatViewSet
│   │   ├── services.py                # get_available_seats(), apply_pricing_rule()
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── migrations/
│   │
│   ├── bookings/                      # Booking & ticket management
│   │   ├── models.py                  # Booking, Ticket, TicketValidationScan
│   │   ├── serializers.py
│   │   ├── viewsets.py                # BookingViewSet, TicketViewSet
│   │   ├── services.py                # create_booking(), validate_ticket(), cancel_booking()
│   │   ├── urls.py
│   │   ├── signals.py                 # Post-booking workflows (emit notifications, etc.)
│   │   ├── admin.py
│   │   └── migrations/
│   │
│   ├── finance/                       # Wallet, transactions, payments
│   │   ├── models.py                  # Wallet, Transaction, Payment, Coupon, CouponUse
│   │   ├── serializers.py
│   │   ├── viewsets.py                # WalletViewSet, TransactionViewSet, CouponViewSet
│   │   ├── services.py                # charge_wallet(), process_refund(), approve_withdrawal()
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── migrations/
│   │
│   ├── concessions/                   # Food, inventory, orders
│   │   ├── models.py                  # FoodItem, FoodCombo, FoodInventory, FoodOrder
│   │   ├── serializers.py
│   │   ├── viewsets.py                # FoodItemViewSet, FoodOrderViewSet
│   │   ├── services.py                # create_food_order(), manage_inventory()
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── migrations/
│   │
│   ├── campaigns/                     # Marketing, promotions, campaigns
│   │   ├── models.py                  # VendorCampaign, VendorCampaignPromoCode, HomeSlide, Banner
│   │   ├── serializers.py
│   │   ├── viewsets.py                # CampaignViewSet, PromocodeViewSet
│   │   ├── services.py                # validate_promo_code(), get_home_content()
│   │   ├── urls.py
│   │   ├── admin.py
│   │   └── migrations/
│   │
│   └── notifications/                 # Push notifications, alerts
│       ├── models.py                  # Notification
│       ├── serializers.py
│       ├── viewsets.py
│       ├── services.py                # send_booking_notification(), send_refund_alert()
│       ├── urls.py
│       ├── admin.py
│       ├── tasks.py                   # Celery tasks (optional)
│       └── migrations/
│
├── tests/
│   ├── __init__.py
│   ├── auth/
│   ├── catalog/
│   ├── venues/
│   ├── bookings/
│   ├── finance/
│   ├── concessions/
│   ├── campaigns/
│   └── notifications/
│
└── requirements.txt
```

---

## Phase 2: Setup & Preparation

### 2.1 Create Core App First

```bash
# In backend/
python manage.py startapp core apps/core
```

**File: `apps/core/models.py`**
```python
from django.db import models
from django.utils import timezone

class TimestampedModel(models.Model):
    """Abstract base model with created_at and updated_at timestamps."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class BaseModel(TimestampedModel):
    """Extended base with is_active flag and common fields."""
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True
```

### 2.2 Move Shared Code to Core

1. **Move middleware:**
   - Copy `app/middleware.py` → `apps/core/middleware.py`

2. **Move permissions:**
   - Copy `app/permissions.py` → `apps/core/permissions.py`
   - Create `apps/core/exceptions.py` for custom exceptions

3. **Move utilities:**
   - Copy `app/utils.py` → `apps/core/utils.py`
   - Copy `app/selectors.py` → `apps/core/selectors.py`

**File: `apps/core/__init__.py`**
```python
default_app_config = 'core.apps.CoreConfig'
```

### 2.3 Update Settings

**File: `backend/settings.py`**
```python
INSTALLED_APPS = [
    # Django defaults
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party
    'rest_framework',
    'corsheaders',
    
    # Project apps (core first to resolve abstract models)
    'apps.core',
    'apps.auth',
    'apps.catalog',
    'apps.venues',
    'apps.bookings',
    'apps.finance',
    'apps.concessions',
    'apps.campaigns',
    'apps.notifications',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.middleware.RoleBasedAccessMiddleware',  # Updated path
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

---

## Phase 3: Safe Model Migration Strategy

### Critical: Zero Data Loss Migration

#### 3.1 Strategy: Use `db_table` to Maintain Database Integrity

When moving models between apps, Django's migration system expects table names to stay the same. We'll use `Meta.db_table` to ensure this.

**Why this matters:**
- Foreign keys reference table names in the database
- Django's `contenttype` framework caches table mappings
- Existing migrations reference `app.ModelName` identifiers

#### 3.2 Step-by-Step Model Migration Process

For each model (example: moving `User` to `auth` app):

1. **Create the new app:**
   ```bash
   python manage.py startapp auth apps/auth
   ```

2. **Define model in new location with same `db_table`:**
   
   **File: `apps/auth/models.py`**
   ```python
   from django.db import models
   from apps.core.models import TimestampedModel
   from django.contrib.auth.hashers import make_password, check_password, identify_hasher

   class User(TimestampedModel):
       phone_number = models.CharField(max_length=13, unique=True)
       email = models.EmailField(unique=True)
       username = models.CharField(max_length=50, unique=True, blank=True, null=True)
       # ... other fields ...
       
       class Meta:
           db_table = "users"  # CRITICAL: Keep existing table name
           app_label = 'auth'

       # ... methods unchanged ...
   ```

3. **Create initial migration in new app:**
   ```bash
   python manage.py makemigrations auth --name initial --empty
   ```

4. **Remove model from old app `app/models.py`** (delete the class)

5. **Create migration to delete model from old app:**
   ```bash
   python manage.py makemigrations app --name remove_user
   ```
   This generates a `DeleteModel` operation which we'll handle next.

6. **Edit the delete migration to preserve the table:**
   
   **File: `app/migrations/000X_remove_user.py`**
   ```python
   from django.db import migrations

   class Migration(migrations.Migration):
       dependencies = [
           ('app', '000Y_previous'),  # Previous migration in old app
           ('auth', '0001_initial'),   # Make it depend on new app's initial
       ]

       operations = [
           # Don't use DeleteModel - use RunSQL to keep table
           migrations.RunSQL(
               sql="ALTER TABLE users RENAME TABLE users_old;",  # Empty operation - do nothing
               reverse_sql=migrations.RunSQL.noop,
           ),
       ]
   ```

   Actually, **better approach:** Just don't create a DeleteModel operation. Instead:

   **File: `app/migrations/000X_move_user_to_auth.py`**
   ```python
   from django.db import migrations

   class Migration(migrations.Migration):
       dependencies = [
           ('app', '000Y_previous'),
           ('auth', '0001_initial'),
       ]

       operations = [
           # Empty - table remains, model just moved to new app
       ]
   ```

7. **Update ForeignKey references** (see Section 3.3)

---

### 3.3 Handling ForeignKey Relationships

#### Challenge: Cross-App Foreign Keys

When models reference each other across apps, handle relationships carefully.

**Scenario 1: Self-contained within one app**
```python
# In apps/bookings/models.py
class Booking(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE)
    # Ticket and Booking both in same app - no problem
```

**Scenario 2: Foreign key to model in different app**
```python
# In apps/bookings/models.py
from apps.venues.models import Vendor

class Booking(models.Model):
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name='bookings'
    )
    # Explicit app label not needed - Django resolves it
```

**Scenario 3: Prevent circular imports**
```python
# In apps/bookings/models.py
from django.db import models

class Booking(models.Model):
    # Use string reference to avoid circular imports
    vendor = models.ForeignKey(
        'venues.Vendor',  # String reference
        on_delete=models.CASCADE,
        related_name='bookings'
    )
```

**Scenario 4: Optional backward compatibility (if an external app imports from monolithic app)**

Create a proxy model in the old `app` for backward compatibility:

```python
# In old app/models.py (kept for compatibility)
from apps.auth.models import User as AuthUser

# Proxy - old code can still import from here
class User(AuthUser):
    class Meta:
        proxy = True
        app_label = 'app'  # Keep in old app for compatibility
```

Then gradually update imports.

---

## Phase 4: Migration Execution (Step-by-Step)

### 4.1 Create Apps in Correct Order

```bash
cd backend/

# Core first (has abstract models)
python manage.py startapp core apps/core

# Then apps with no internal dependencies
python manage.py startapp auth apps/auth
python manage.py startapp catalog apps/catalog

# Then interdependent apps
python manage.py startapp venues apps/venues
python manage.py startapp bookings apps/bookings
python manage.py startapp finance apps/finance

# Then dependent apps
python manage.py startapp concessions apps/concessions
python manage.py startapp campaigns apps/campaigns
python manage.py startapp notifications apps/notifications
```

### 4.2 Model Dependency Map (Migration Order)

```
1. core                          (abstract models only)
   └─ No dependencies

2. auth                          (User, Admin)
   └─ Depends on: core

3. catalog                       (Movie, Review, etc.)
   └─ Depends on: core, auth (for user reviews)

4. venues                        (Vendor, Show, Screen, Seat)
   └─ Depends on: core, auth, catalog

5. bookings                      (Booking, Ticket)
   └─ Depends on: core, venues, catalog, payments

6. finance                       (Wallet, Transaction, Payment)
   └─ Depends on: core, auth, venues, bookings

7. concessions                   (FoodItem, FoodOrder)
   └─ Depends on: core, venues, bookings, finance

8. campaigns                     (VendorCampaign, Banner)
   └─ Depends on: core, venues, finance

9. notifications                 (Notification)
   └─ Depends on: core, auth, bookings, finance
```

### 4.3 Detailed Migration for Each Model

**Step 1: Move models to apps in a single batch**

For each app, create `models.py` with models from the old app. Example:

```python
# apps/auth/models.py
from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from apps.core.models import TimestampedModel

class User(TimestampedModel):
    phone_number = models.CharField(max_length=13, unique=True)
    email = models.EmailField(unique=True)
    # ... copy all fields ...
    
    class Meta:
        db_table = "users"
        app_label = 'auth'
        
    # ... copy all methods unchanged ...

class Admin(TimestampedModel):
    # ... similar ...
    class Meta:
        db_table = "admins"
        app_label = 'admin'  # Or 'auth' if preferred
```

**Step 2: Create migrations for all new apps**

```bash
python manage.py makemigrations core auth catalog venues bookings finance concessions campaigns notifications
```

**Step 3: Inspect migrations for ForeignKey issues**

Django will generate migrations with:
- `CreateModel` operations for all models with `db_table` set
- Likely errors if cross-app ForeignKeys aren't properly resolved

**Step 4: Remove from old app and create deletion migration**

Edit `app/models.py` to remove all migrated classes.

```bash
python manage.py makemigrations app --name cleanup_migrate_to_multiple_apps
```

**Step 5: Apply migrations carefully**

```bash
# Backupfirst
python manage.py dumpdata > backup_pre_migration.json
python manage.py migrate --plan  # Dry-run to see what will happen
python manage.py migrate          # Apply all
```

If issues arise:
```bash
python manage.py migrate --fake app 000X  # Fake a specific migration
```

---

## Phase 5: Update Import Paths

### 5.1 Update All Imports Systematically

Use VS Code find-and-replace or script to update imports.

**Old imports → New imports:**

```python
# OLD
from app.models import User, Movie, Booking
from app.serializers import UserSerializer
from app.services import create_booking

# NEW
from apps.auth.models import User
from apps.catalog.models import Movie
from apps.bookings.models import Booking
from apps.auth.serializers import UserSerializer
from apps.bookings.services import create_booking
```

### 5.2 Find-and-Replace Strategy

Using PowerShell (Windows):

```powershell
# Find all imports of specific module
Get-ChildItem -Path "backend/" -Include "*.py" -Recurse | 
  Select-String -Pattern "from app\.models import"

# Replace pattern
Get-ChildItem -Path "backend/" -Include "*.py" -Recurse | 
  ForEach-Object {
    (Get-Content $_) -replace 'from app\.(\w+) import', 'from apps.$1 import' | 
    Set-Content $_
  }
```

### 5.3 Update URL Configuration

**File: `backend/urls.py`**

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.auth.urls')),
    path('api/catalog/', include('apps.catalog.urls')),
    path('api/venues/', include('apps.venues.urls')),
    path('api/bookings/', include('apps.bookings.urls')),
    path('api/finance/', include('apps.finance.urls')),
    path('api/concessions/', include('apps.concessions.urls')),
    path('api/campaigns/', include('apps.campaigns.urls')),
    path('api/notifications/', include('apps.notifications.urls')),
]
```

---

## Phase 6: Service Layer Refactoring

### 6.1 Split `services.py` by Domain

Each app should have its own `services.py` with domain-specific business logic.

**Old structure:**
```python
# app/services.py (3000+ lines)
def create_booking(): ...
def charge_wallet(): ...
def get_movies(): ...
def send_notification(): ...
```

**New structure:**
```python
# apps/bookings/services.py
def create_booking(): ...
def cancel_booking(): ...

# apps/finance/services.py
def charge_wallet(): ...
def process_refund(): ...
def approve_withdrawal(): ...

# apps/catalog/services.py
def get_featured_movies(): ...
def search_movies(): ...

# apps/notifications/services.py
def send_booking_notification(): ...
def send_refund_alert(): ...
```

### 6.2 Cross-App Service Calls

When one app's service needs to call another:

```python
# apps/bookings/services.py
from apps.finance.services import charge_wallet
from apps.notifications.services import send_booking_notification

def create_booking(booking_data):
    booking = Booking.objects.create(**booking_data)
    
    # Call finance service
    charge_wallet(booking.vendor, booking.total_price)
    
    # Call notification service
    send_booking_notification(booking)
    
    return booking
```

### 6.3 Avoid Circular Imports

Strategy: Import inside functions when needed:

```python
# apps/bookings/services.py
def create_booking(booking_data):
    from apps.finance.services import charge_wallet  # Import here, not at top
    booking = Booking.objects.create(**booking_data)
    charge_wallet(...)
```

Or use signals for loose coupling:

```python
# apps/bookings/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Booking

@receiver(post_save, sender=Booking)
def on_booking_created(sender, instance, created, **kwargs):
    if created:
        from apps.finance.services import charge_wallet
        from apps.notifications.services import send_booking_notification
        
        charge_wallet(instance.vendor, instance.total_price)
        send_booking_notification(instance)
```

---

## Phase 7: Test Thoroughly

### 7.1 Create Test Suite Structure

```
tests/
├── __init__.py
├── conftest.py                 # Pytest fixtures
├── auth/
│   ├── test_models.py
│   ├── test_views.py
│   └── test_services.py
├── bookings/
│   ├── test_models.py
│   ├── test_views.py
│   └── test_services.py
└── ... (for all apps)
```

### 7.2 Test Database Integrity

```python
# tests/test_migrations.py
from django.test import TestCase
from django.db import connection
from django.core.management import call_command

class MigrationTests(TestCase):
    def test_all_tables_exist(self):
        """Ensure all expected tables exist after migration."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'YOUR_DB_NAME'
            """)
            tables = {row[0] for row in cursor.fetchall()}
            
            expected_tables = {
                'users', 'admins', 'movies', 'shows', 
                'bookings', 'wallets', 'transactions', ...
            }
            
            missing = expected_tables - tables
            self.assertEqual(missing, set(), 
                f"Missing tables: {missing}")

    def test_foreign_keys_intact(self):
        """Ensure all ForeignKey relationships still work."""
        # Test sample data retrieval across apps
        from apps.bookings.models import Booking
        from apps.venues.models import Vendor
        
        booking = Booking.objects.first()
        self.assertIsNotNone(booking.vendor)
        self.assertTrue(isinstance(booking.vendor, Vendor))
```

### 7.3 Run Migrations in Test Database

```bash
# Test migrations create all tables without error
python manage.py test --keepdb

# Manual database integrity check
python manage.py migrate  # Test DB
python manage.py shell
>>> from django.db import connection
>>> cursor = connection.cursor()
>>> cursor.execute("SELECT COUNT(*) FROM users")
>>> print(cursor.fetchone())  # Should show existing user count

# Verify API endpoints still work
python manage.py runserver
# Test endpoints in Postman
```

---

## Phase 8: Backward Compatibility (Optional)

If external code imports from old `app` module, create compatibility shims:

```python
# app/__init__.py (keep for backward compatibility)
# This allows existing code to still work during transition

from apps.auth.models import User, Admin
from apps.catalog.models import Movie, Review
from apps.venues.models import Vendor, Show
from apps.bookings.models import Booking, Ticket
from apps.finance.models import Wallet, Transaction
from apps.concessions.models import FoodItem, FoodOrder
from apps.campaigns.models import VendorCampaign, Banner
from apps.notifications.models import Notification

# Deprecation warning
import warnings
warnings.warn(
    "Importing from 'app' is deprecated. Import app-specific modules instead. "
    "Example: from apps.bookings.models import Booking",
    DeprecationWarning,
    stacklevel=2
)

__all__ = [
    'User', 'Admin', 'Movie', 'Review', 'Vendor', 'Show',
    'Booking', 'Ticket', 'Wallet', 'Transaction', 'FoodItem',
    'FoodOrder', 'VendorCampaign', 'Banner', 'Notification'
]
```

---

## Phase 9: Final Checklist

### Pre-Deployment Verification

- [ ] All migrations pass: `python manage.py migrate --check`
- [ ] No circular imports: Run app and check console for warnings
- [ ] All tests pass: `python manage.py test`
- [ ] Database data integrityverified (record counts match)
- [ ] API endpoints respond correctly
- [ ] Admin interface works for all models
- [ ] Git history clean: `git log --oneline` shows logical commits
- [ ] Settings updated with new INSTALLED_APPS
- [ ] Middleware references updated
- [ ] URL config includes all app includes
- [ ] Frontend API calls still work (if applicable)
- [ ] No hardcoded imports to old `app` module remain

### Post-Deployment Checks

```bash
# Verify in production
python manage.py shell
>>> from apps.auth.models import User
>>> User.objects.count()  # Should show same count as before
>>> from apps.bookings.models import Booking
>>> Booking.objects.first().vendor  # Cross-app relationship works
```

---

## Phase 10: Recommended Best Practices Going Forward

### 10.1 App Naming Conventions

- **Singular app names** (not plural): `booking` not `bookings`
- **English nouns**: `catalog`, `venue`, `transaction`
- **No underscores**: `concessions` not `food_items`

### 10.2 File Organization Within Each App

```
apps/booking/
├── migrations/
│   ├── __init__.py
│   ├── 0001_initial.py
│   └── ...
├── __init__.py
├── admin.py                # Django admin config
├── apps.py                 # App config
├── models.py               # Data models
├── serializers.py          # DRF serializers
├── viewsets.py             # DRF viewsets
├── views.py                # Function-based views (if needed)
├── services.py             # Business logic
├── signals.py              # Django signals
├── urls.py                 # URL routing
├── permissions.py          # Model-specific permissions
├── filters.py              # DRF filters
├── throttles.py            # Rate limiting
├── pagination.py           # Custom pagination
├── exceptions.py           # App-specific exceptions
├── tests/
│   ├── __init__.py
│   ├── test_models.py
│   ├── test_views.py
│   ├── test_services.py
│   ├── test_serializers.py
│   ├── factories.py        # Test data factories
│   └── fixtures.json       # JSON fixtures
└── fixtures/
    └── initial_data.json
```

### 10.3 Service Layer Best Practices

```python
# apps/booking/services.py

def create_booking(booking_data: dict) -> Booking:
    """
    Create a new booking with full business logic.
    
    Args:
        booking_data: Dict with keys (user, show, seats, total_price)
        
    Returns:
        Booking instance
        
    Raises:
        InsufficientWalletBalance: If customer wallet insufficient
        SeatNotAvailable: If seats already booked
    """
    from apps.finance.services import charge_wallet
    from apps.notifications.services import send_notification
    
    with transaction.atomic():
        # 1. Validate business rules
        if not _validate_seat_availability(booking_data['seats']):
            raise SeatNotAvailable("Seats already booked")
        
        # 2. Create model instance
        booking = Booking.objects.create(**booking_data)
        
        # 3. Execute cross-app business logic
        charge_wallet(booking.user.wallet, booking.total_price)
        
        # 4. Emit signals for other apps to react
        booking_created.send(sender=Booking, instance=booking)
        
    return booking


def _validate_seat_availability(seats):
    """Private helper - doesn't pollute module namespace."""
    from .models import BookedSeat
    return not BookedSeat.objects.filter(seat__in=seats).exists()
```

### 10.4 Avoid Common Mistakes

❌ **DON'T: Create models in multiple apps that reference the same table**
```python
# BAD - two apps, one table
class User(models.Model):  # In apps/auth/models.py
    class Meta:
        db_table = "users"

class User(models.Model):  # In apps/profile/models.py (WRONG!)
    class Meta:
        db_table = "users"
```

✅ **DO: One model definition per table**
```python
# GOOD
class User(models.Model):
    class Meta:
        db_table = "users"

# In other apps, import and use via ForeignKey
from apps.auth.models import User
```

❌ **DON'T: Have circular imports**
```python
# BAD - creates import loop
# apps/booking/services.py
from apps.notification.services import send_notification

# apps/notification/services.py
from apps.booking.services import get_booking_details
```

✅ **DO: Use signals for loose coupling**
```python
# GOOD - apps are independent
# apps/booking/signals.py - sends signal after booking created
booking_created = Signal()

# apps/notification/listeners.py - listens to signal
@receiver(booking_created, sender=Booking)
def notify_on_booking(sender, instance, **kwargs):
    send_notification(...)
```

### 10.5 Settings Organization

```python
# backend/settings/
├── __init__.py
├── base.py              # Shared settings
├── development.py       # Extensions for dev
├── production.py        # Extensions for prod
└── testing.py           # Test-specific settings
```

```python
# base.py
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'apps.core',
    'apps.auth',
    # ... all apps
]

# development.py
from .base import *

DEBUG = True
INSTALLED_APPS += ['django_extensions', 'debug_toolbar']
```

### 10.6 URL Structure

```python
# backend/urls.py
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.auth.urls', namespace='auth')),
    path('api/catalog/', include('apps.catalog.urls', namespace='catalog')),
    # ... etc
]

# Usage in templates/frontend
reverse('auth:login')     # /api/auth/login/
reverse('booking:list')   # /api/booking/bookings/
```

---

## Migration Command Reference

```bash
# Show migration status
python manage.py showmigrations

# Create migrations for all apps
python manage.py makemigrations --dry-run  # See what would run
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Fake migrations (when moving models between apps)
python manage.py migrate --fake auth 0001_initial

# Create empty migration (for custom SQL)
python manage.py makemigrations app_name --empty --name custom_migration

# Rollback migrations
python manage.py migrate app_name 0001  # Go back to 0001
python manage.py migrate app_name zero  # Rollback all

# Show SQL for migration
python manage.py sqlmigrate auth 0001

# Squash migrations (after stable)
python manage.py squashmigrations auth 0001 0010
```

---

## Troubleshooting Guide

### Issue: "No such table" after migration

**Cause:** Migration didn't use correct `db_table` or `app_label`

**Fix:**
```python
# In model
class Meta:
    db_table = "original_table_name"
    app_label = 'new_app'
```

### Issue: ForeignKey "app.ModelName doesn't exist"

**Cause:** Cross-app reference not set up correctly

**Fix:**
```python
# Use string reference
vendor = models.ForeignKey('venues.Vendor', on_delete=models.CASCADE)
```

### Issue: Circular import when running server

**Cause:** Two apps importing from each other at module level

**Fix:**
```python
# Import inside functions
def my_function():
    from apps.other_app.models import SomeModel
    return SomeModel.objects.all()
```

### Issue: Django admin shows old table names

**Cause:** Contenttype cache not invalidated

**Fix:**
```bash
python manage.py migrate --fake-initial
python manage.py dumpdata --natural-foreign > backup.json
python manage.py flush --no-input
python manage.py loaddata backup.json
```

---

## Quick Start Checklist

If you're ready to start, follow this order:

1. **Create feature branch**: `git checkout -b refactor/multi-app`
2. **Backup database**: `python manage.py dumpdata > backup.json`
3. **Update settings.py**: Add new INSTALLED_APPS
4. **Create apps**: Run `python manage.py startapp` for each
5. **Copy models**: Move classes to respective `models.py`
6. **Set db_table**: Add `Meta.db_table` and `app_label` to each model
7. **Create initial migrations**: `python manage.py makemigrations`
8. **Test migrations**: `python manage.py migrate --plan`
9. **Apply migrations**: `python manage.py migrate`
10. **Update imports**: Replace `from app` with `from apps.xxx`
11. **Copy services/views/urls**: Move to respective app directories
12. **Update URL config**: Add all app includes to `backend/urls.py`
13. **Run tests**: `python manage.py test`
14. **Deploy**: Commit and push

---

**Next**: Follow Phase 2-4 to begin the refactoring. Start with the core app, then move to auth, catalog, venues in order. Each step should be committed to git with clear messages like `"refactor: move auth models to new app"`.
