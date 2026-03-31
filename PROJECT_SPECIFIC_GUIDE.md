# Ticket System Refactoring - Project-Specific Guide
## How to Apply the Multi-App Architecture to Your Project

Based on analysis of your current codebase, here's how to specifically refactor your ticket booking system.

---

## Your Current Architecture Analysis

### Current Models (20+ models in single app)

```
🔐 Auth (4 models)
├── User
├── Admin
├── LoginAttempt
└── OTPVerification

🎬 Catalog (6 models)
├── Movie
├── MovieGenre
├── MovieMovieGenre
├── Person (actors/directors)
├── MovieCredit
└── Review

📺 Venues (7 models)
├── Vendor
├── VendorStaff
├── Show
├── Screen
├── Seat
├── SeatCategory
├── PricingRule
└── VendorCancellationPolicy

🎫 Bookings (3 models)
├── Booking
├── Ticket
└── TicketValidationScan

💳 Finance (7 models)
├── Wallet
├── Transaction
├── Payment
├── Coupon
├── CouponUse
├── VendorCampaign
└── VendorCampaignPromoCode

🍿 Food (4 models)
├── FoodItem
├── FoodCombo
├── FoodInventory
└── FoodOrder (implied: FoodOrderItem)

📢 Content (3 models)
├── HomeSlide
├── Banner
└── Collaborator
└── CollabDetails
└── Notification
```

### Current View Organization (Already Good!)

Your views are nicely organized by feature:
```
views/
├── admin_home.py       → Move to finance app (admin dashboard)
├── auth.py             → Move to auth app
├── booking.py          → Move to bookings app
├── bookings.py         → Move to bookings app
├── coupons.py          → Move to finance app
├── food.py             → Move to concessions app
├── home.py             → Move to campaigns app
├── movies.py           → Move to catalog app
├── notifications.py    → Move to notifications app
├── seats.py            → Move to venues app
├── shows.py            → Move to venues app
├── ticket_validation.py → Move to bookings app
├── users.py            → Move to auth app
└── vendors.py          → Move to venues app
```

This is perfect - you already have feature-based organization at the view level!

---

## Step-by-Step Refactoring for Your Project

### Step 1: Analyze Model Dependencies

Before moving models, map their relationships:

```
User → LoginAttempt (1:M)
User → OTPVerification (implicit, via phone_number)
User → Booking (1:M, ForeignKey)

Movie → Show (1:M)
Movie → Review (1:M)
Movie → MovieCredit (1:M)
Movie → MovieGenre (M:M via MovieMovieGenre)

Vendor → Show (1:M)
Vendor → Screen (1:M)
Vendor → Seat (indirect via Screen)
Vendor → VendorStaff (1:M)
Vendor → PricingRule (1:M)
Vendor → VendorCancellationPolicy (1:M)
Vendor → Wallet (1:1)

Booking → User (FK)
Booking → Show (FK)
Booking → Vendor (FK)
Booking → Ticket (1:M)
Booking → Payment (1:M)
Booking → Coupon (M:M via CouponUse)

Wallet → Vendor (1:1)
Wallet → Transaction (1:M)
Transaction → Vendor (FK)

FoodItem → Vendor (FK)
FoodItem → FoodCombo (M:M)
FoodItem → FoodInventory (1:M)
FoodOrder → FoodItem (M:M)
FoodOrder → Booking (FK)

VendorCampaign → Vendor (FK)
VendorCampaignPromoCode → VendorCampaign (FK)

Notification → User/Admin/Vendor (recipient)

HomeSlide → Movie (FK)
Banner → Movie (FK)
```

### Step 2: Create Apps Directory

```bash
cd backend

# Create apps parent directory
mkdir apps
touch apps/__init__.py

# Create all sub-apps
python manage.py startapp core apps/core
python manage.py startapp auth apps/auth
python manage.py startapp catalog apps/catalog
python manage.py startapp venues apps/venues
python manage.py startapp bookings apps/bookings
python manage.py startapp finance apps/finance
python manage.py startapp concessions apps/concessions
python manage.py startapp campaigns apps/campaigns
python manage.py startapp notifications apps/notifications
```

### Step 3: Move Models with db_table

For each model class, add `class Meta` with `db_table` to preserve existing table names:

**Example: Moving User from app to apps/auth**

```python
# apps/auth/models.py
from django.db import models
from apps.core.models import TimestampedModel

class User(TimestampedModel):
    phone_number = models.CharField(max_length=13, unique=True)
    email = models.EmailField(unique=True)
    # ... (copy all existing fields) ...
    
    class Meta:
        db_table = "users"  # CRITICAL - keep existing table name
        app_label = 'auth'  # Explicit app label
        
    # ... (copy all methods unchanged) ...
```

**Key Points:**
- Copy the ENTIRE model class as-is
- Add `db_table = "original_table_name"` to Meta
- Don't modify field names or types
- Keep all methods (set_password, check_password, etc.)

### Step 4: Model Distribution for Your Project

#### **apps/core/models.py** (Abstract only)
```python
class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class BaseModel(TimestampedModel):
    is_active = models.BooleanField(default=True)
    class Meta:
        abstract = True
```

#### **apps/auth/models.py** (4 models)
```python
class User(TimestampedModel):
    class Meta:
        db_table = "users"

class Admin(TimestampedModel):
    class Meta:
        db_table = "admins"

class LoginAttempt(models.Model):
    class Meta:
        db_table = "login_attempts"

class OTPVerification(models.Model):
    class Meta:
        db_table = "otp_verifications"
```

#### **apps/catalog/models.py** (6 models)
```python
class Movie(models.Model):
    class Meta:
        db_table = "movies"

class MovieGenre(models.Model):
    class Meta:
        db_table = "movie_genres"

class MovieMovieGenre(models.Model):
    class Meta:
        db_table = "movie_movie_genres"

class Person(models.Model):
    class Meta:
        db_table = "persons"  # Or "people"

class MovieCredit(models.Model):
    class Meta:
        db_table = "movie_credits"

class Review(models.Model):
    class Meta:
        db_table = "reviews"
```

#### **apps/venues/models.py** (8 models)
```python
from apps.auth.models import User  # For vendor staff

class Vendor(models.Model):
    commission_percent = models.DecimalField(...)  # From your finance work
    class Meta:
        db_table = "vendors"

class VendorStaff(models.Model):
    class Meta:
        db_table = "vendor_staffs"

class Show(models.Model):
    movie = models.ForeignKey('catalog.Movie', ...)  # Cross-app reference
    class Meta:
        db_table = "shows"

class Screen(models.Model):
    class Meta:
        db_table = "screens"

class Seat(models.Model):
    class Meta:
        db_table = "seats"

class SeatCategory(models.Model):
    class Meta:
        db_table = "seat_categories"

class PricingRule(models.Model):
    class Meta:
        db_table = "pricing_rules"

class VendorCancellationPolicy(models.Model):
    class Meta:
        db_table = "vendor_cancellation_policies"
```

#### **apps/bookings/models.py** (3 models)
```python
from apps.auth.models import User
from apps.venues.models import Vendor, Show

class Booking(models.Model):
    user = models.ForeignKey(User, ...)
    vendor = models.ForeignKey(Vendor, ...)
    show = models.ForeignKey(Show, ...)
    class Meta:
        db_table = "bookings"

class Ticket(models.Model):
    class Meta:
        db_table = "tickets"

class TicketValidationScan(models.Model):
    class Meta:
        db_table = "ticket_validation_scans"
```

#### **apps/finance/models.py** (7 models)
```python
from apps.venues.models import Vendor
from apps.auth.models import User

class Wallet(models.Model):
    vendor = models.OneToOneField(Vendor, ...)
    class Meta:
        db_table = "wallets"

class Transaction(models.Model):
    # Types from your implementation
    TYPE_BOOKING_REVERSAL = "BOOKING_REVERSAL"
    TYPE_PLATFORM_COMMISSION = "PLATFORM_COMMISSION"
    TYPE_PLATFORM_COMMISSION_REVERSAL = "PLATFORM_COMMISSION_REVERSAL"
    class Meta:
        db_table = "transactions"

class Payment(models.Model):
    class Meta:
        db_table = "payments"

class Coupon(models.Model):
    class Meta:
        db_table = "coupons"

class CouponUse(models.Model):
    class Meta:
        db_table = "coupon_uses"

class VendorCampaign(models.Model):
    vendor = models.ForeignKey(Vendor, ...)
    class Meta:
        db_table = "vendor_campaigns"

class VendorCampaignPromoCode(models.Model):
    campaign = models.ForeignKey(VendorCampaign, ...)
    class Meta:
        db_table = "vendor_campaign_promo_codes"
```

#### **apps/concessions/models.py** (4 models)
```python
from apps.venues.models import Vendor

class FoodItem(models.Model):
    vendor = models.ForeignKey(Vendor, ...)
    class Meta:
        db_table = "food_items"

class FoodCombo(models.Model):
    class Meta:
        db_table = "food_combos"

class FoodInventory(models.Model):
    class Meta:
        db_table = "food_inventory"

class FoodOrder(models.Model):
    class Meta:
        db_table = "food_orders"
```

#### **apps/campaigns/models.py** (3 models)
```python
from apps.catalog.models import Movie

class HomeSlide(models.Model):
    movie = models.ForeignKey(Movie, ...)
    class Meta:
        db_table = "home_slides"

class Banner(models.Model):
    movie = models.ForeignKey(Movie, ...)
    class Meta:
        db_table = "banners"

class Collaborator(models.Model):
    class Meta:
        db_table = "collaborators"

class CollabDetails(models.Model):
    class Meta:
        db_table = "collab_details"
```

#### **apps/notifications/models.py** (1 model)
```python
class Notification(models.Model):
    class Meta:
        db_table = "notifications"
```

### Step 5: Move Views to Their Apps

Your views are already well-organized! Just move them:

```bash
# Move to apps/auth/views.py
mv app/views/auth.py apps/auth/views.py
mv app/views/users.py apps/auth/users.py  # or merge into views.py

# Move to apps/catalog/views.py
mv app/views/movies.py apps/catalog/views.py

# Move to apps/venues/views.py
mv app/views/shows.py apps/venues/views.py
mv app/views/seats.py apps/venues/views.py
mv app/views/vendors.py apps/venues/views.py

# Move to apps/bookings/views.py
mv app/views/booking.py apps/bookings/views.py
mv app/views/bookings.py apps/bookings/bookings.py  # or merge
mv app/views/ticket_validation.py apps/bookings/views.py  # append to views

# Move to apps/finance/views.py
mv app/views/admin_home.py apps/finance/admin_home.py  # or new file
mv app/views/coupons.py apps/finance/coupons.py

# Move to apps/concessions/views.py
mv app/views/food.py apps/concessions/views.py

# Move to apps/campaigns/views.py
mv app/views/home.py apps/campaigns/views.py

# Move to apps/notifications/views.py
mv app/views/notifications.py apps/notifications/views.py
```

### Step 6: Merge Duplicate View Files

You have `booking.py` and `bookings.py` - merge them:

```python
# apps/bookings/views.py
# Contents of both files combined
from rest_framework.decorators import api_view
from .models import Booking, Ticket
from .serializers import BookingSerializer
from .services import create_booking, cancel_booking

# From booking.py
@api_view(['GET'])
def get_booking(request, booking_id):
    ...

# From bookings.py
@api_view(['POST'])
def create_booking_view(request):
    ...

# From ticket_validation.py
@api_view(['POST'])
def validate_ticket(request):
    ...
```

### Step 7: Organize Imports for Cross-App References

**Example: Booking model needs Movie**

```python
# apps/bookings/models.py
from django.db import models
from apps.venues.models import Vendor, Show
from apps.auth.models import User
from apps.catalog.models import Movie

class Booking(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE)
    movie = models.ForeignKey(Movie, on_delete=models.CASCADE)
    show = models.ForeignKey(Show, on_delete=models.CASCADE)
    # ... fields ...
    
    class Meta:
        db_table = "bookings"
```

**For circular imports, use strings:**

```python
# apps/bookings/models.py
class Booking(models.Model):
    # Don't import Show directly to avoid circular dependency
    show = models.ForeignKey('venues.Show', on_delete=models.CASCADE)
```

### Step 8: Split services.py

Your monolithic `services.py` needs to be split. Here's the mapping:

```
Old: app/services.py (3000+ lines)
New structure:

apps/auth/services.py
├── register_user()
├── authenticate_user()
├── change_password()
└── password_reset()

apps/catalog/services.py
├── get_featured_movies()
├── search_movies()
├── get_movie_details()
└── add_movie_review()

apps/venues/services.py
├── create_venue()
├── get_available_seats()
├── apply_pricing_rule()
└── validate_seat_availability()

apps/bookings/services.py
├── create_booking()
├── validate_ticket()
├── cancel_booking()
└── _apply_booking_cancellation_with_policy()

apps/finance/services.py
├── charge_wallet()
├── process_refund()
├── approve_withdrawal()
├── list_admin_withdrawal_requests()
└── _resolve_vendor_commission_percent()

apps/concessions/services.py
├── create_food_order()
├── manage_inventory()
└── get_available_food_items()

apps/campaigns/services.py
├── get_home_slides()
├── validate_promo_code()
└── apply_coupon()

apps/notifications/services.py
├── send_booking_notification()
├── send_refund_alert()
└── send_otp_sms()
```

### Step 9: Migration Strategy for Your Project

1. **Backup first:**
   ```bash
   python manage.py dumpdata > backup_before_refactor.json
   ```

2. **Check table names in your database:**
   ```bash
   python manage.py dbshell
   ```
   Then execute:
   ```sql
   SHOW TABLES;
   ```
   
   Your existing tables are:
   - users
   - admins
   - movies
   - shows
   - bookings
   - vendors
   - etc.

3. **Make migrations for all new apps:**
   ```bash
   python manage.py makemigrations core auth catalog venues bookings finance concessions campaigns notifications
   ```

4. **Create a "transition" migration in old app:**
   Create `app/migrations/000X_transition_to_multiapp.py`:
   
   ```python
   from django.db import migrations

   class Migration(migrations.Migration):
       dependencies = [
           ('app', '000Y_last_migration'),
           ('core', '0001_initial'),
           ('auth', '0001_initial'),
           ('catalog', '0001_initial'),
           ('venues', '0001_initial'),
           ('bookings', '0001_initial'),
           ('finance', '0001_initial'),
           ('concessions', '0001_initial'),
           ('campaigns', '0001_initial'),
           ('notifications', '0001_initial'),
       ]

       operations = [
           # Empty - all data already preserved by db_table
       ]
   ```

5. **Apply migrations:**
   ```bash
   python manage.py migrate --plan  # Review first
   python manage.py migrate
   ```

### Step 10: Update All Imports

**Find and Replace in VS Code:**

Open Find and Replace (Ctrl+H) and apply these:

```
OLD → NEW

from app\.models import → from apps.APPNAME.models import
from app\.serializers import → from apps.APPNAME.serializers import
from app\.services import → from apps.APPNAME.services import
from app\.views import → from apps.APPNAME.views import
from app\.permissions import → from apps.core.permissions import
from app\.middleware import → from apps.core.middleware import
from app\.utils import → from apps.core.utils import
from app\.selectors import → from apps.core.selectors import
```

**Example Find-and-Replace in PowerShell:**

```powershell
$files = Get-ChildItem -Path "backend/apps" -Include "*.py" -Recurse

foreach($file in $files) {
    $content = Get-Content $file.FullName -Raw
    
    # Replace patterns
    $content = $content -replace 'from app\.models', 'from apps.XXX.models'
    $content = $content -replace 'from app\.serializers', 'from apps.XXX.serializers'
    $content = $content -replace 'from app\.services', 'from apps.XXX.services'
    
    Set-Content -Path $file.FullName -Value $content
}
```

### Step 11: Update backend/urls.py

```python
# backend/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API routes
    path('api/auth/', include('apps.auth.urls', namespace='auth')),
    path('api/catalog/', include('apps.catalog.urls', namespace='catalog')),
    path('api/venues/', include('apps.venues.urls', namespace='venues')),
    path('api/bookings/', include('apps.bookings.urls', namespace='bookings')),
    path('api/finance/', include('apps.finance.urls', namespace='finance')),
    path('api/concessions/', include('apps.concessions.urls', namespace='concessions')),
    path('api/campaigns/', include('apps.campaigns.urls', namespace='campaigns')),
    path('api/notifications/', include('apps.notifications.urls', namespace='notifications')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### Step 12: Update backend/settings.py

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third-party
    'rest_framework',
    'corsheaders',
    
    # Project apps - ORDER MATTERS
    'apps.core',        # First - abstract models
    'apps.auth',        # Second - no internal dependencies
    'apps.catalog',     # Third - depends on auth for reviews
    'apps.venues',      # Fourth - depends on catalog
    'apps.bookings',    # Fifth - depends on venues
    'apps.finance',     # Sixth - depends on bookings
    'apps.concessions', # Seventh - depends on venues
    'apps.campaigns',   # Eighth - depends on catalog
    'apps.notifications', # Last - depends on multiple
]

# Middleware - update path
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.middleware.RoleBasedAccessMiddleware',  # Updated
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

---

## Common Issues for Your Project

### Issue 1: ForeignKey to Movie from Multiple Apps

**Problem:** Show, Banner, HomeSlide, Review all reference Movie

**Solution:** Use string reference:
```python
# In apps/venues/models.py
class Show(models.Model):
    movie = models.ForeignKey('catalog.Movie', on_delete=models.CASCADE)

# In apps/campaigns/models.py
class Banner(models.Model):
    movie = models.ForeignKey('catalog.Movie', on_delete=models.CASCADE)
```

### Issue 2: Cross-App Services Need Each Other

**Problem:** Booking service needs Finance service, which needs Notification service

**Solution:** Use signals for loose coupling:

```python
# apps/bookings/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Booking

booking_created = django.dispatch.Signal()
booking_cancelled = django.dispatch.Signal()

@receiver(post_save, sender=Booking)
def on_booking_created(sender, instance, created, **kwargs):
    if created:
        booking_created.send(sender=Booking, instance=instance)

# apps/finance/listeners.py
from django.dispatch import receiver
from apps.bookings.signals import booking_created

@receiver(booking_created)
def charge_on_booking(sender, instance, **kwargs):
    from .services import charge_wallet
    charge_wallet(instance.vendor.wallet, instance.total_price)

# apps/notifications/listeners.py
from django.dispatch import receiver
from apps.bookings.signals import booking_created

@receiver(booking_created)
def notify_on_booking(sender, instance, **kwargs):
    from .services import send_booking_notification
    send_booking_notification(instance)
```

### Issue 3: Vendor Commission Already in Your Finance Implementation

Your commit includes `commission_percent` field in Vendor model. This should go in:

```python
# apps/venues/models.py
class Vendor(models.Model):
    # ... existing fields ...
    commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Platform commission percentage (0-100). Overrides platform default."
    )
    
    class Meta:
        db_table = "vendors"
```

And `apps/finance/services.py` has the resolution logic:

```python
def _resolve_vendor_commission_percent(vendor):
    """
    Get effective commission percentage for vendor.
    Uses vendor override or falls back to platform default.
    """
    from django.conf import settings
    
    if vendor.commission_percent is not None:
        return min(max(vendor.commission_percent, 0), 100)  # Bounds 0-100
    
    return getattr(settings, 'DEFAULT_COMMISSION_PERCENT', 10.0)
```

---

## Execution Checklist for Your Project

- [ ] Read both refactoring guides
- [ ] Create `apps/` directory: `mkdir backend/apps && touch backend/apps/__init__.py`
- [ ] Create all 9 new apps (core, auth, catalog, venues, bookings, finance, concessions, campaigns, notifications)
- [ ] Copy abstract models to `core/models.py`
- [ ] Copy model classes to respective apps with `db_table` preserved
- [ ] Copy views and merge duplicates
- [ ] Copy and split `services.py`
- [ ] Create `urls.py` in each app
- [ ] Create `serializers.py` in each app  
- [ ] Backup database: `python manage.py dumpdata > backup.json`
- [ ] Update `backend/settings.py` with new INSTALLED_APPS
- [ ] Update `backend/urls.py` with includes from each app
- [ ] Move middleware/permissions to core app
- [ ] Generate migrations: `python manage.py makemigrations`
- [ ] Review plan: `python manage.py migrate --plan`
- [ ] Apply migrations: `python manage.py migrate`
- [ ] Update all imports (find-and-replace)
- [ ] Run tests: `python manage.py test`
- [ ] Verify API endpoints work
- [ ] Git commit: `git commit -m "refactor: split monolithic app into multi-app architecture"`

---

## Next Actions

1. **Start with core app** - Set up abstract models and shared utilities
2. **Then auth app** - No dependencies needed
3. **Then catalog** - Independent except optional User review foreign key
4. **Then venues** - Depends on catalog (Show→Movie)
5. **Then bookings** - Depends on venues and auth
6. **Then finance** - Depends on bookings and venues
7. **Then concessions** - Depends on venues
8. **Then campaigns** - Depends on catalog
9. **Finally notifications** - Depends on potentially everything

Each app creation and migration should be a separate git commit so history is clean.

Good luck! Your existing view structure makes this much easier than a completely disorganized codebase.
