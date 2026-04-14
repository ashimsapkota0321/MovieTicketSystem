"""
COMPREHENSIVE GUIDE: DEBUGGING RESEND EMAIL INTEGRATION IN DJANGO
=================================================================

This guide helps you debug and fix email sending issues with Resend API in your
Mero Ticket Django application.

Table of Contents:
1. Quick Start - Verify Your Setup (5 minutes)
2. Common Issues & Solutions
3. Step-by-Step Debugging Process
4. Working Examples
5. Testing Endpoints
6. Production Checklist
"""

# =============================================================================
# 1. QUICK START - VERIFY YOUR SETUP
# =============================================================================

"""
STEP 1: Check Environment Configuration
========================================

Your .env.local (or .env) file should contain:

    RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    RESEND_FROM_EMAIL="Mero Ticket <noreply@yourdomain.com>"
    RESEND_API_BASE_URL=https://api.resend.com

CRITICAL: 
- API key must start with 're_' (Resend production key)
- From email domain must be verified with Resend
- Don't use onboarding@resend.dev in production


STEP 2: Run Configuration Check
================================

    python manage.py debug_email check

Expected output:
    ✓ RESEND_API_KEY: Set
    ✓ RESEND_FROM_EMAIL: Set
    ✓ Email Format: Valid
    ✓ Configuration looks GOOD


STEP 3: Test API Connectivity
==============================

    python manage.py debug_email connectivity

Expected output:
    ✓ Testing endpoint: https://api.resend.com/emails
    ✓ Connectivity: ✓ Success (HTTP 200)


STEP 4: Send Test Email
=======================

    python manage.py debug_email test --email your-email@example.com

Expected output:
    ✓ Success! Email accepted with ID: xxxxx
    ✓ Email has been sent to Resend for delivery
"""

# =============================================================================
# 2. COMMON ISSUES & SOLUTIONS
# =============================================================================

"""
ISSUE 1: "RESEND_API_KEY is not set"
====================================

Symptom:
- debug_email shows "✗ RESEND_API_KEY: Not set"
- Emails never send

Solution:
1. Create/edit .env.local in project root:
   
   RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

2. Restart Django server (Ctrl+C, then manage.py runserver)

3. Verify in shell:
   python manage.py shell
   >>> from django.conf import settings
   >>> print(settings.RESEND_API_KEY)
   re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx

If still None:
- Check .env file is in correct location (project root)
- Ensure no typos in variable name
- Make sure .env is readable and not in .gitignore


ISSUE 2: HTTP 401 Unauthorized
================================

Symptom:
- "HTTP 401: Unauthorized" error
- API key appears to be set

Solutions:
A. Invalid API Key Format:
   - API key must start with 're_'
   - Check for typos or extra spaces
   - Regenerate from: https://resend.com/settings/api-keys

B. Expired Key:
   - Check Resend dashboard if key was regenerated
   - Get fresh key: https://resend.com/settings/api-keys
   - Update .env and restart server

C. Key Authentication Issues:
   - Make sure Bearer token is added: "Bearer {api_key}"
   - Check Content-Type header: "application/json"


ISSUE 3: HTTP 422 Validation Error
==================================

Symptom:
- "HTTP 422: Validation Error"
- Response shows specific field errors

Common Causes:

A. Unverified Domain:
   Error: {"message": "Domain not verified or invalid"}
   
   Fix:
   1. Go to https://resend.com/domains
   2. Click "Add Domain"
   3. Enter your domain (without www)
   4. Update DNS records (CNAME or MX)
   5. Wait for verification
   6. Check status: python manage.py debug_email domain

B. Invalid From Email:
   Error: {"message": "Invalid from email format"}
   
   Valid formats:
   - "noreply@mydomain.com"
   - "Mero Ticket <noreply@mydomain.com>"
   - "support+tag@mydomain.com"
   
   Invalid:
   - "random@onboarding.resend.dev" (only during testing)
   - "noreply" (missing domain)

C. Invalid Recipient Email:
   - Ensure recipient email is valid format
   - Missing @ symbol
   - Extra spaces

D. Missing Required Fields:
   - subject: Must be present and non-empty
   - message (text): Must be present
   - to: Must be array with at least one valid email


ISSUE 4: Emails Not Appearing in Inbox
======================================

Symptom:
- send_test_email returns success
- Email doesn't arrive in inbox

Causes & Solutions:

A. Check Spam/Junk:
   - Gmail: Check Spam tab
   - Outlook: Check Junk folder
   - Yahoo: Check Spam folder

B. Review DNS Records:
   - SPF records not configured
   - DKIM not enabled
   - DMARC missing
   
   Fix in Resend:
   1. Dashboard → Domains → Select domain
   2. Copy DNS records
   3. Update domain's DNS settings
   4. Wait 24-48 hours for propagation

C. Test with Personal Email First:
   - Use your own email to test
   - Avoid corporate email filters
   - Some corporate filters block Resend IPs

D. Check API Response Email ID:
   If you see: "Email accepted with ID: xxxxx"
   - Email was accepted by Resend
   - Go to https://resend.com/emails
   - Search for the ID to see delivery status


ISSUE 5: "Connection Refused" or Network Error
==============================================

Symptom:
- Cannot reach Resend API
- "URLError" in logs

Causes:

A. No Internet Connection:
   - Check if you can ping google.com
   - Check firewall/proxy settings

B. Resend API Down (Rare):
   - Check https://status.resend.com
   - Try again in a few minutes

C. Proxy/Firewall Blocking:
   - If behind corporate network
   - Ask IT to whitelist api.resend.com
   - Port 443 must be open for HTTPS


ISSUE 6: Emails Sent from Django Console, But Not From Views
============================================================

Symptom:
- python manage.py shell → send_test_email() works
- But emails never send from normal Django flow

Causes:

A. backgroundJob Queue Not Processing:
   - Check if background jobs are enabled
   - Run: python manage.py process_background_jobs
   - Or set up celery/APScheduler

B. Exception in Email Sending:
   - Check DEBUG logs in settings
   - Enable logging to see errors

C. Email Queuing but Not Sending:
   - Check BackgroundJob table:
     SELECT * FROM app_backgroundjob WHERE job_type='notification_email'
   - Look for stuck jobs with status='processing'

Fix:
from app.services.core import _send_notification_email
sent = _send_notification_email(
    subject="Test",
    message="Test message",
    recipient_email="test@example.com"
)
print(f"Sent: {sent}")
"""

# =============================================================================
# 3. STEP-BY-STEP DEBUGGING PROCESS
# =============================================================================

"""
DEBUGGING FLOWCHART
===================

START
  ↓
[1] Run: python manage.py debug_email health
  ├─→ Errors found? → Fix configuration (see Issue 1-5)
  │
[2] Email still not sending from code?
  ├─→ Add logging to your email function
  │
[3] Run: python manage.py debug_email test --email your@email.com
  ├─→ Test succeeds but production doesn't?
  │   └─→ Check if BackgroundJob queue is processing
  │
[4] Still failing?
  └─→ Check logs and enable verbose logging


DETAILED STEPS
==============

Step 1: Enable Verbose Logging
------------------------------
In your view or function that sends email, add:

    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"Attempting to send email to {recipient_email}")
    logger.info(f"Subject: {subject}")
    
    sent = _send_notification_email(
        subject=subject,
        message=message,
        recipient_email=recipient_email,
    )
    
    logger.info(f"Email send result: {sent}")

Then check logs:
    tail -f /path/to/logs/django.log


Step 2: Test with Direct API Call
----------------------------------
In Django shell:

    python manage.py shell
    
    from app.email_debug import debug_email_send
    
    result = debug_email_send(
        to="test@example.com",
        subject="Test Subject",
        message="Test Message"
    )
    
    print(result)

Expected result:
    {
        'to': 'test@example.com',
        'success': True,
        'errors': []
    }


Step 3: Check Configuration at Runtime
---------------------------------------
    from django.conf import settings
    from app.email_debug import check_resend_config
    
    config = check_resend_config()
    print(config)
    
    # Check specific values
    print(f"API Key: {settings.RESEND_API_KEY[:5]}...")
    print(f"From Email: {settings.RESEND_FROM_EMAIL}")
    print(f"Backend: {settings.EMAIL_BACKEND}")


Step 4: Monitor Background Jobs
--------------------------------
If using background job queue:

    from app.models import BackgroundJob
    
    # Check pending emails
    pending = BackgroundJob.objects.filter(
        job_type='notification_email',
        status='pending'
    )
    print(f"Pending emails: {pending.count()}")
    
    # Process them
    from app.services.core import process_background_jobs
    result = process_background_jobs()
    print(result)
    # Output: {'claimed': X, 'processed': Y, 'completed': Z, 'failed': W, 'requeued': R}


Step 5: Manual API Test
-----------------------
If all else fails, test with curl:

    curl -X POST "https://api.resend.com/emails" \\
      -H "Authorization: Bearer re_YOUR_API_KEY" \\
      -H "Content-Type: application/json" \\
      -d '{
        "from": "noreply@yourdomain.com",
        "to": "test@example.com",
        "subject": "Test",
        "text": "Test message"
      }'

Expected response:
    {"id":"xxxxx","from":"...","to":["..."],"created_at":"..."}
"""

# =============================================================================
# 4. WORKING EXAMPLES
# =============================================================================

"""
EXAMPLE 1: Simple Email Function
==================================

from django.conf import settings
from app.services.core import _send_notification_email

def send_welcome_email(user):
    '''Send welcome email to new user.'''
    success = _send_notification_email(
        subject=f"Welcome to Mero Ticket, {user.first_name}!",
        message=f"Hi {user.first_name}, welcome to our platform!",
        recipient_email=user.email,
        html_message=f'''
        <div style="font-family: Arial, sans-serif;">
            <h2>Welcome to Mero Ticket!</h2>
            <p>Hi {user.first_name},</p>
            <p>Thank you for joining us!</p>
        </div>
        '''
    )
    
    if success:
        print(f"Welcome email sent to {user.email}")
    else:
        print(f"Failed to send welcome email to {user.email}")
    
    return success


EXAMPLE 2: Email with OTP
==========================

from django.conf import settings
from app.services.core import _send_notification_email, _build_password_reset_otp_html

def send_otp_email(email, otp):
    '''Send OTP for password reset.'''
    html = _build_password_reset_otp_html(otp)
    
    return _send_notification_email(
        subject="Your Mero Ticket Password Reset Code",
        message=f"Your reset code is: {otp}",
        recipient_email=email,
        html_message=html
    )


EXAMPLE 3: Email in View
========================

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from app.services.core import _send_notification_email

@api_view(['POST'])
def register(request):
    '''Register user and send welcome email.'''
    # ... validation and user creation ...
    
    user = User.objects.create_user(
        email=request.data['email'],
        username=request.data['username'],
        # ... other fields ...
    )
    
    # Send welcome email asynchronously (or use background job)
    email_sent = _send_notification_email(
        subject="Welcome to Mero Ticket!",
        message="Welcome to our platform!",
        recipient_email=user.email
    )
    
    return Response({
        'user_id': user.id,
        'email_sent': email_sent
    }, status=status.HTTP_201_CREATED)


EXAMPLE 4: Batch Email Send
============================

from app.models import User
from app.services.core import _send_notification_email

def send_newsletter(subject, message):
    '''Send newsletter to all active users.'''
    users = User.objects.filter(is_active=True)
    
    sent_count = 0
    failed_count = 0
    
    for user in users:
        try:
            success = _send_notification_email(
                subject=subject,
                message=message,
                recipient_email=user.email
            )
            if success:
                sent_count += 1
            else:
                failed_count += 1
        except Exception as e:
            print(f"Error sending to {user.email}: {e}")
            failed_count += 1
    
    return {
        'sent': sent_count,
        'failed': failed_count,
        'total': sent_count + failed_count
    }


EXAMPLE 5: Error Handling with Logging
======================================

import logging
from app.services.core import _send_notification_email

logger = logging.getLogger(__name__)

def send_booking_confirmation(booking):
    '''Send booking confirmation with error handling.'''
    user = booking.user
    
    try:
        html_message = f'''
        <div>
            <h2>Booking Confirmed</h2>
            <p>Booking ID: {booking.id}</p>
            <p>Show: {booking.showtime.movie.title}</p>
            <p>Date: {booking.showtime.start_time}</p>
        </div>
        '''
        
        success = _send_notification_email(
            subject=f"Booking Confirmed - {booking.id}",
            message=f"Your booking {booking.id} has been confirmed",
            recipient_email=user.email,
            html_message=html_message
        )
        
        if success:
            logger.info(f"Booking confirmation sent to {user.email}")
            return True
        else:
            logger.warning(f"Failed to send booking confirmation to {user.email}")
            return False
            
    except Exception as e:
        logger.exception(f"Error sending booking confirmation: {e}")
        return False
"""

# =============================================================================
# 5. TESTING ENDPOINTS
# =============================================================================

"""
TEST API ENDPOINT
=================

Add this to your views to test email functionality:

views/debug.py:
    
    from rest_framework.decorators import api_view
    from rest_framework.response import Response
    from app.services.core import _send_notification_email
    from app.email_debug import run_full_health_check
    
    @api_view(['GET'])
    def email_health_check(request):
        '''Health check endpoint for email system.'''
        if not request.user.is_staff:
            return Response({'error': 'Unauthorized'}, status=403)
        
        health = run_full_health_check()
        return Response(health)
    
    @api_view(['POST'])
    def send_test_email_endpoint(request):
        '''Send test email (admin only).'''
        if not request.user.is_staff:
            return Response({'error': 'Unauthorized'}, status=403)
        
        recipient = request.data.get('recipient_email')
        if not recipient:
            return Response({'error': 'recipient_email required'}, status=400)
        
        success = _send_notification_email(
            subject="Test Email",
            message="This is a test email",
            recipient_email=recipient
        )
        
        return Response({
            'sent': success,
            'recipient': recipient
        })

urls.py:
    
    from django.urls import path
    from app.views.debug import email_health_check, send_test_email_endpoint
    
    urlpatterns = [
        # ... other patterns ...
        path('api/debug/email/health/', email_health_check, name='email-health'),
        path('api/debug/email/test/', send_test_email_endpoint, name='test-email'),
    ]

Usage:
    
    # Check health
    curl http://localhost:8000/api/debug/email/health/
    
    # Send test
    curl -X POST http://localhost:8000/api/debug/email/test/ \\
         -H "Content-Type: application/json" \\
         -d '{"recipient_email": "test@example.com"}'
"""

# =============================================================================
# 6. PRODUCTION CHECKLIST
# =============================================================================

"""
BEFORE GOING TO PRODUCTION
===========================

☐ Configuration:
  ☐ RESEND_API_KEY set in environment (not in code)
  ☐ RESEND_FROM_EMAIL configured
  ☐ API key starts with 're_'
  ☐ DEBUG=False in production
  
☐ Domain Setup:
  ☐ Custom domain added to Resend
  ☐ Domain verified with Resend
  ☐ DNS records updated (SPF, DKIM, DMARC)
  ☐ Domain not using onboarding@resend.dev
  
☐ Testing:
  ☐ Run: python manage.py debug_email health
  ☐ Send test email to personal email
  ☐ Check email arrives in inbox (not spam)
  ☐ Test from staging environment
  
☐ Error Handling:
  ☐ Logging configured for email errors
  ☐ Graceful fallback if email fails
  ☐ User feedback if email sending fails
  
☐ Background Jobs:
  ☐ Process background jobs in task queue
  ☐ Monitor job processing
  ☐ Set up cronjob for job processor if needed
  
☐ Monitoring:
  ☐ Monitor email logs in production
  ☐ Set up alerts for email failures
  ☐ Track email delivery rates

ENVIRONMENT VARIABLES TEMPLATE
==============================

Production .env:

    # Resend Configuration
    RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    RESEND_FROM_EMAIL="Mero Ticket <noreply@yourdomain.com>"
    RESEND_API_BASE_URL=https://api.resend.com
    
    # Django Configuration
    EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend  # or other backend
    DEBUG=False
    
    # Database
    DB_ENGINE=django.db.backends.mysql
    DB_NAME=production_db
    DB_USER=prod_user
    DB_PASSWORD=secure_password
    DB_HOST=db.example.com
    DB_PORT=3306


EMAIL SETUP COMMANDS
====================

# 1. Verify configuration
python manage.py debug_email check

# 2. Test connectivity
python manage.py debug_email connectivity

# 3. Verify domain
python manage.py debug_email domain

# 4. Send test email
python manage.py debug_email test --email your@email.com

# 5. Full health check
python manage.py debug_email health

# 6. Process background jobs
python manage.py process_background_jobs
"""

# =============================================================================
# QUICK REFERENCE
# =============================================================================

"""
QUICK COMMANDS
==============

# Check if API key is set
python manage.py shell
>>> from django.conf import settings
>>> settings.RESEND_API_KEY

# Send test email
>>> from app.email_debug import send_test_email
>>> send_test_email('your-email@example.com')

# Run full diagnostics
>>> from app.email_debug import run_full_health_check
>>> run_full_health_check()

# Send email directly
>>> from app.services.core import _send_notification_email
>>> _send_notification_email('Subject', 'Message', 'recipient@example.com')

# Check background jobs
>>> from app.models import BackgroundJob
>>> BackgroundJob.objects.filter(job_type='notification_email').count()


LOG FILES
=========

Check these files for email-related logs:
- /var/log/django.log
- /var/log/mail.log
- Application error logs in Django project


HELPFUL LINKS
=============

- Resend Docs: https://resend.com/docs
- Resend API Keys: https://resend.com/settings/api-keys
- Resend Domains: https://resend.com/domains  
- Resend Email Status: https://resend.com/emails
- Resend Status Page: https://status.resend.com
"""

print(__doc__)
