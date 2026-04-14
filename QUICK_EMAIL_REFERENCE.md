"""
MERO TICKET EMAIL DEBUGGING - QUICK REFERENCE CARD
===================================================

Created: April 2026
Purpose: Fast debugging and testing of Resend email integration
Version: 1.0
"""

# =============================================================================
# STEP 1: VERIFY ENVIRONMENT SETUP (2 minutes)
# =============================================================================

"""
Check your .env.local or .env file contains:

    RESEND_API_KEY=re_your_actual_api_key_here
    RESEND_FROM_EMAIL="Mero Ticket <noreply@yourdomain.com>"
    RESEND_API_BASE_URL=https://api.resend.com

CRITICAL CHECKLIST:
    ✓ RESEND_API_KEY starts with 're_'
    ✓ No extra spaces or quotes in API key
    ✓ From email has valid format: "Name <email@domain>" or "email@domain"
    ✓ Domain in email is verified with Resend
    ✓ Not using onboarding@resend.dev in production
"""

# =============================================================================
# STEP 2: RUN DIAGNOSTIC TESTS
# =============================================================================

"""
COMMAND 1: Check Configuration
────────────────────────────────
    cd /path/to/mero-ticket/backend
    python manage.py debug_email check

Expected: All items show ✓ with green checkmarks


COMMAND 2: Test API Connectivity
─────────────────────────────────
    python manage.py debug_email connectivity

Expected: ✓ Connectivity: ✓ Success (HTTP 200)


COMMAND 3: Verify Domain
────────────────────────
    python manage.py debug_email domain

Expected: ✓ Verification Status: ✓ VERIFIED


COMMAND 4: Send Test Email
──────────────────────────
    python manage.py debug_email test --email your-email@example.com

Expected: ✓ Success! Email accepted with ID: xxxxx
         Email should arrive within 5-10 seconds


COMMAND 5: Full System Health Check
───────────────────────────────────
    python manage.py debug_email health

Expected: All checks show ✓
"""

# =============================================================================
# STEP 3: DJANGO SHELL TESTING
# =============================================================================

"""
Interactive Testing in Django Shell:
────────────────────────────────────

# Start Django shell
python manage.py shell

# Test 1: Quick test
>>> from app.email_test_fixtures import quick_test
>>> quick_test("your-email@example.com")

# Test 2: Run all test suite
>>> from app.email_test_fixtures import run_all_tests
>>> results = run_all_tests("your-email@example.com")

# Test 3: Test specific email type
>>> from app.email_test_fixtures import test_otp_email, test_html_email
>>> test_html_email("your-email@example.com")

# Test 4: Create a real test from your models
>>> from app.models import User
>>> from app.services.core import _send_notification_email
>>> user = User.objects.first()
>>> _send_notification_email(
...     subject="Welcome!",
...     message="Test message",
...     recipient_email=user.email
... )
"""

# =============================================================================
# STEP 4: COMMON ERRORS & QUICK FIXES
# =============================================================================

"""
ERROR 1: ✗ RESEND_API_KEY is not set
─────────────────────────────────────
Cause: Environment variable not loaded
Fix:   1. Add to .env.local: RESEND_API_KEY=re_xxxxx
       2. Restart Django: Ctrl+C then python manage.py runserver
       3. Verify: python manage.py debug_email check


ERROR 2: HTTP 401 Unauthorized
──────────────────────────────
Cause: Invalid or wrong API key
Fix:   1. Go to https://resend.com/settings/api-keys
       2. Regenerate new API key
       3. Copy full key starting with 're_'
       4. Update .env.local with exact key
       5. Restart Django server


ERROR 3: HTTP 422 Validation Error - "Domain not verified"
──────────────────────────────────────────────────────────
Cause: Your domain isn't verified with Resend
Fix:   1. Visit https://resend.com/domains
       2. Click "Add Domain"
       3. Enter your domain (e.g., yourdomain.com)
       4. Copy DNS records shown
       5. Add DNS records to your domain provider
       6. Wait 24-48 hours for verification
       7. Check: python manage.py debug_email domain


ERROR 4: HTTP 422 - Invalid from email format
──────────────────────────────────────────────
Cause: From email has wrong format
Fix:   Valid formats:
       - "noreply@yourdomain.com"
       - "Mero Ticket <noreply@yourdomain.com>"
       
       Invalid:
       - "random.address@onboarding.resend.dev"
       - "noreply" (missing domain)


ERROR 5: Email sent but not received
────────────────────────────────────
Cause: Probably in spam folder or DNS not configured
Fix:   1. Check spam/junk folders
       2. Configure DNS SPF/DKIM/DMARC
       3. Go to: https://resend.com/domains/{domain}
       4. Copy all DNS records
       5. Add to your domain provider
       6. Test with personal email first


ERROR 6: Cannot reach Resend API
────────────────────────────────
Cause: Network/firewall issue
Fix:   1. Check internet: ping google.com
       2. Test directly: curl https://api.resend.com
       3. Check firewall allows HTTPS (port 443)
       4. If corporate: ask IT to whitelist api.resend.com
"""

# =============================================================================
# STEP 5: VERIFY EMAIL IN CODE
# =============================================================================

"""
Using in Views:
───────────────

from rest_framework.response import Response
from app.services.core import _send_notification_email

@api_view(['POST'])
def register(request):
    # Create user...
    user = User.objects.create(...)
    
    # Send email
    email_sent = _send_notification_email(
        subject="Welcome to Mero Ticket!",
        message="Welcome aboard!",
        recipient_email=user.email
    )
    
    if email_sent:
        print("✓ Email sent successfully")
    else:
        print("✗ Email send failed")
    
    return Response({'user_id': user.id, 'email_sent': email_sent})


Handling Errors:
────────────────

from app.services.core import _send_notification_email
import logging

logger = logging.getLogger(__name__)

def send_important_email(recipient):
    try:
        success = _send_notification_email(
            subject="Important Update",
            message="Check your account",
            recipient_email=recipient
        )
        
        if success:
            logger.info(f"Email sent to {recipient}")
        else:
            logger.warning(f"Email send failed for {recipient}")
            # Fallback: queue for retry or notify admin
        
        return success
        
    except Exception as e:
        logger.exception(f"Error sending email: {e}")
        return False
"""

# =============================================================================
# STEP 6: PRODUCTION DEPLOYMENT
# =============================================================================

"""
Before Going Live:
──────────────────

Checklist:
☐ .env file has RESEND_API_KEY set (not hardcoded)
☐ Custom domain verified with Resend
☐ DNS records (SPF, DKIM, DMARC) configured
☐ Run: python manage.py debug_email health → All ✓
☐ Send test email → Received in inbox
☐ Check logs for any errors
☐ Background job queue configured to process emails
☐ Email error handling in place
☐ Monitoring/logging set up

Environment Variables (Production):
───────────────────────────────────
RESEND_API_KEY=<your_production_api_key>
RESEND_FROM_EMAIL="Company <noreply@yourdomain.com>"
DEBUG=False
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend

Background Job Processing:
──────────────────────────
# If using background jobs for emails, process them regularly:

# Option 1: Manual batch processing (Django admin/shell)
from app.services.core import process_background_jobs
result = process_background_jobs()
print(result)  # Shows: completed, failed, requeued counts

# Option 2: Celery task (if available)
# See your project's task queue setup

# Option 3: Cronjob (Linux/Unix)
*/5 * * * * cd /app && python manage.py process_background_jobs > /var/log/email-jobs.log 2>&1
"""

# =============================================================================
# WHAT TO DO NEXT
# =============================================================================

"""
IMMEDIATE NEXT STEPS:
═════════════════════

1. RUN DIAGNOSTICS (5 min)
   ✓ cd backend
   ✓ python manage.py debug_email health
   ✓ Fix any red ✗ items found

2. GET API KEY (2 min)
   ✓ Visit: https://resend.com/settings/api-keys
   ✓ Create new API key or copy existing
   ✓ Add to .env.local

3. VERIFY DOMAIN (30 sec)
   ✓ Check current domain: python manage.py debug_email domain
   ✓ If not verified: add domain to Resend

4. SEND TEST (2 min)
   ✓ python manage.py debug_email test --email your@email.com
   ✓ Should arrive in 5-10 seconds

5. TEST IN CODE (10 min)
   ✓ python manage.py shell
   ✓ from app.email_test_fixtures import run_all_tests
   ✓ run_all_tests("your@email.com")
   ✓ Verify success message

If everything passes → You're ready to send emails!
If tests fail → Check the specific error above and fix


HELPFUL RESOURCES:
══════════════════

API Key Management:
  https://resend.com/settings/api-keys

Domain Verification:
  https://resend.com/domains

Email Status:
  https://resend.com/emails

API Documentation:
  https://resend.com/docs

Status/Incidents:
  https://status.resend.com


COMMANDS REFERENCE:
═════════════════════

Check Configuration:
  python manage.py debug_email check

Test Connectivity:
  python manage.py debug_email connectivity

Verify Domain:
  python manage.py debug_email domain

Send Test Email:
  python manage.py debug_email test --email to@example.com

Full Health Check:
  python manage.py debug_email health

Django Shell Testing:
  python manage.py shell
  from app.email_test_fixtures import quick_test
  quick_test("your@email.com")

Check Background Jobs:
  python manage.py shell
  from app.models import BackgroundJob
  BackgroundJob.objects.filter(job_type='notification_email').count()
"""

# =============================================================================
# TROUBLESHOOTING DECISION TREE
# =============================================================================

"""
START HERE
    │
    ├─→ Can't access Resend API?
    │   └─→ See ERROR 6: Cannot reach Resend API
    │
    ├─→ Getting 401 Unauthorized?
    │   └─→ See ERROR 2: HTTP 401 Unauthorized
    │
    ├─→ Getting 422 Validation Error?
    │   ├─→ Domain not verified → See ERROR 3
    │   └─→ Invalid email format → See ERROR 4
    │
    ├─→ Email sent but not received?
    │   └─→ See ERROR 5: Email sent but not received
    │
    ├─→ RESEND_API_KEY not found?
    │   └─→ See ERROR 1: RESEND_API_KEY is not set
    │
    ├─→ Emails work in shell, not in views?
    │   └─→ Check background job processing
    │   └─→ Check logs for exceptions
    │
    └─→ Still stuck?
        ├─→ Check: https://resend.com/docs
        ├─→ Email: support@resend.com
        └─→ Check all logs in: backend/logs/ or /var/log/
"""

print(__doc__)
