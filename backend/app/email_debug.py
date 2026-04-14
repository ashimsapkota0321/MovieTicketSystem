"""
Email debugging utility for Resend API integration.
Use this for troubleshooting email sending issues.

Usage:
# In Django shell or views:
from app.email_debug import *

# 1. Check configuration
check_resend_config()

# 2. Verify API connectivity
test_resend_api_connectivity()

# 3. Send test email
send_test_email("recipient@example.com")

# 4. Debug a failed send
debug_email_send(
    to="test@example.com",
    subject="Test",
    message="Test message"
)
"""

import json
import logging
from typing import Any, Optional
from django.conf import settings
from urllib import request as urllib_request
from urllib import error as urllib_error

logger = logging.getLogger(__name__)


def print_section(title: str) -> None:
    """Pretty print a section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_status(key: str, value: Any, is_secure: bool = False) -> None:
    """Pretty print a status line."""
    display_value = "***REDACTED***" if is_secure and value else value
    print(f"✓ {key}: {display_value}")


def print_error(key: str, value: Any) -> None:
    """Pretty print an error line."""
    print(f"✗ {key}: {value}")


def print_warning(key: str, value: Any) -> None:
    """Pretty print a warning line."""
    print(f"⚠ {key}: {value}")


# ============================================================================
# 1. CONFIGURATION CHECKS
# ============================================================================

def check_resend_config() -> dict[str, Any]:
    """
    Verify all Resend configuration settings.
    Returns a config status dictionary.
    """
    print_section("RESEND CONFIGURATION CHECK")
    
    config = {
        "api_key_set": False,
        "api_key_valid": False,
        "from_email_set": False,
        "from_email_valid": False,
        "api_url_set": False,
        "fallback_backend": False,
        "issues": [],
    }

    # Check API Key
    api_key = str(getattr(settings, "RESEND_API_KEY", "") or "").strip()
    if api_key:
        config["api_key_set"] = True
        print_status("RESEND_API_KEY", "Set", is_secure=True)
        
        # Validate format (should start with re_)
        if api_key.startswith("re_"):
            config["api_key_valid"] = True
            print_status("API Key Format", "Valid (starts with 're_')", is_secure=True)
        else:
            config["api_key_valid"] = False
            config["issues"].append("API key doesn't start with 're_' - may be invalid format")
            print_warning("API Key Format", "May be invalid - should start with 're_'")
    else:
        config["issues"].append("RESEND_API_KEY is not set in environment")
        print_error("RESEND_API_KEY", "Not set")

    # Check From Email
    from_email = str(getattr(settings, "RESEND_FROM_EMAIL", "") or "").strip()
    if from_email:
        config["from_email_set"] = True
        print_status("RESEND_FROM_EMAIL", from_email)
        
        if "@" in from_email or "<" in from_email:
            config["from_email_valid"] = True
            print_status("Email Format", "Valid")
        else:
            config["issues"].append("RESEND_FROM_EMAIL has invalid format")
            print_warning("Email Format", "Invalid format - should be 'name <email@domain>' or 'email@domain'")
    else:
        default_from = str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
        if default_from:
            from_email = default_from
            print_status("Using DEFAULT_FROM_EMAIL", from_email)
        else:
            config["issues"].append("Both RESEND_FROM_EMAIL and DEFAULT_FROM_EMAIL are not set")
            print_error("From Email", "Not configured")

    # Check API URL
    api_url = str(getattr(settings, "RESEND_API_BASE_URL", "") or "").strip()
    if api_url:
        config["api_url_set"] = True
        print_status("RESEND_API_BASE_URL", api_url)
    else:
        print_warning("API URL", "Using default https://api.resend.com")

    # Check EMAIL_BACKEND
    email_backend = str(getattr(settings, "EMAIL_BACKEND", "") or "").strip()
    print_status("EMAIL_BACKEND", email_backend)
    if "console" in email_backend.lower():
        config["fallback_backend"] = True
        print_warning("Backend", "Using console backend (DEV MODE) - emails won't actually send")

    # Summary
    print()
    if config["api_key_set"] and config["from_email_set"] and config["api_key_valid"]:
        print("✓ Configuration looks GOOD")
    else:
        print("✗ Configuration has ISSUES:")
        for issue in config["issues"]:
            print(f"  - {issue}")

    return config


# ============================================================================
# 2. RESEND API CONNECTIVITY
# ============================================================================

def test_resend_api_connectivity() -> bool:
    """
    Test if we can reach the Resend API endpoint.
    """
    print_section("RESEND API CONNECTIVITY TEST")
    
    api_key = str(getattr(settings, "RESEND_API_KEY", "") or "").strip()
    if not api_key:
        print_error("API Key", "Not configured - skipping connectivity test")
        return False

    api_url = str(
        getattr(settings, "RESEND_API_BASE_URL", "") or "https://api.resend.com"
    ).strip().rstrip("/")
    
    endpoint = f"{api_url}/emails"
    print_status("Testing endpoint", endpoint)

    # Prepare a minimal request with Authorization header
    request_obj = urllib_request.Request(
        endpoint,
        data=json.dumps({
            "from": "test@example.com",
            "to": ["test@example.com"],
            "subject": "Test",
            "text": "Test",
        }).encode("utf-8"),
        method="POST",
    )
    request_obj.add_header("Authorization", f"Bearer {api_key}")
    request_obj.add_header("Content-Type", "application/json")

    try:
        with urllib_request.urlopen(request_obj, timeout=10) as response:
            status_code = response.getcode()
            if status_code in (200, 201, 202):
                print_status("Connectivity", f"✓ Success (HTTP {status_code})")
                return True
            else:
                print_warning("Connectivity", f"Unexpected status {status_code}")
                return False
    except urllib_error.HTTPError as exc:
        status_code = exc.code
        try:
            error_body = exc.read().decode("utf-8", errors="ignore")
            error_data = json.loads(error_body)
            error_msg = error_data.get("message", error_body)
        except:
            error_msg = str(exc)
        
        print_error(f"HTTP {status_code}", error_msg)
        
        # Common Resend errors
        if status_code == 401:
            print_warning("Issue", "Unauthorized - API key may be invalid or expired")
        elif status_code == 422:
            print_warning("Issue", "Validation error - check email format or domain configuration")
        elif status_code == 429:
            print_warning("Issue", "Rate limited - too many requests")
        
        return False
    except urllib_error.URLError as exc:
        print_error("Network Error", str(exc))
        print_warning("Issue", "Cannot reach Resend API - check internet connectivity")
        return False
    except Exception as exc:
        print_error("Unexpected Error", str(exc))
        return False


# ============================================================================
# 3. DOMAIN VERIFICATION CHECK
# ============================================================================

def check_domain_verification() -> dict[str, Any]:
    """
    Check if your domain is verified with Resend.
    Note: This requires calling the Resend domains API.
    """
    print_section("DOMAIN VERIFICATION STATUS")
    
    api_key = str(getattr(settings, "RESEND_API_KEY", "") or "").strip()
    if not api_key:
        print_error("API Key", "Not configured")
        return {"verified": False, "note": "Configure API key first"}

    from_email = str(getattr(settings, "RESEND_FROM_EMAIL", "") or "").strip()
    if not from_email:
        from_email = str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    
    if not from_email:
        print_error("From Email", "Not configured")
        return {"verified": False, "note": "Configure from email first"}

    # Extract domain
    if "<" in from_email:
        domain = from_email.split("<")[-1].rstrip(">").split("@")[-1]
    elif "@" in from_email:
        domain = from_email.split("@")[-1]
    else:
        domain = None

    if not domain:
        print_error("Domain", "Could not extract domain from email")
        return {"verified": False, "domain": None}

    print_status("Email", from_email)
    print_status("Domain", domain)

    api_url = str(
        getattr(settings, "RESEND_API_BASE_URL", "") or "https://api.resend.com"
    ).strip().rstrip("/")
    endpoint = f"{api_url}/domains"

    request_obj = urllib_request.Request(endpoint, method="GET")
    request_obj.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib_request.urlopen(request_obj, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            domains = data.get("domains", [])
            
            verified = False
            for d in domains:
                if d.get("name") == domain and d.get("status") == "verified":
                    verified = True
                    print_status("Verification Status", "✓ VERIFIED")
                    break
            
            if not verified:
                print_error("Verification Status", "✗ NOT VERIFIED or NOT FOUND")
                print_warning("Fix", f"Verify domain '{domain}' in Resend dashboard: https://resend.com/domains")
                print()
                print("Steps:")
                print("  1. Go to https://resend.com/api/domains")
                print(f"  2. Add domain: {domain}")
                print("  3. Update DNS records as shown")
                print("  4. Wait for verification (can take up to 48 hours)")
            
            return {
                "verified": verified,
                "domain": domain,
                "all_domains": [d.get("name") for d in domains],
            }
    except urllib_error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        print_error(f"API Error (HTTP {exc.code})", error_body)
        return {"verified": False, "error": error_body}
    except Exception as exc:
        print_error("Error", str(exc))
        return {"verified": False, "error": str(exc)}


# ============================================================================
# 4. SEND TEST EMAIL
# ============================================================================

def send_test_email(recipient_email: str) -> bool:
    """
    Send a simple test email to verify everything works.
    
    Args:
        recipient_email: Email address to send test to
    
    Returns:
        True if email was accepted by API, False otherwise
    """
    print_section("SENDING TEST EMAIL")
    
    print_status("Recipient", recipient_email)

    api_key = str(getattr(settings, "RESEND_API_KEY", "") or "").strip()
    if not api_key:
        print_error("API Key", "Not configured - cannot send")
        return False

    from_email = str(getattr(settings, "RESEND_FROM_EMAIL", "") or "").strip()
    if not from_email:
        from_email = str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    if not from_email:
        from_email = "Mero Ticket <onboarding@resend.dev>"
    
    print_status("From", from_email)

    api_url = str(
        getattr(settings, "RESEND_API_BASE_URL", "") or "https://api.resend.com"
    ).strip().rstrip("/")
    endpoint = f"{api_url}/emails"

    payload = {
        "from": from_email,
        "to": [recipient_email],
        "subject": "Mero Ticket - Test Email",
        "text": "This is a test email from Mero Ticket.",
        "html": (
            "<div style='font-family:Arial,sans-serif'>"
            "<h2>Mero Ticket Test Email</h2>"
            "<p>If you received this, email sending is working!</p>"
            "</div>"
        ),
    }

    request_body = json.dumps(payload).encode("utf-8")
    request_obj = urllib_request.Request(
        endpoint,
        data=request_body,
        method="POST",
    )
    request_obj.add_header("Authorization", f"Bearer {api_key}")
    request_obj.add_header("Content-Type", "application/json")

    print()
    print("Sending...")

    try:
        with urllib_request.urlopen(request_obj, timeout=20) as response:
            status_code = response.getcode()
            response_data = json.loads(response.read().decode("utf-8"))
            
            if status_code in (200, 201, 202):
                email_id = response_data.get("id", "unknown")
                print_status("Success!", f"Email accepted with ID: {email_id}")
                print()
                print("✓ Email has been sent to Resend for delivery")
                print("  (It may take a few seconds to appear in the recipient's inbox)")
                return True
            else:
                print_error(f"Unexpected Status", f"HTTP {status_code}")
                return False
    except urllib_error.HTTPError as exc:
        status_code = exc.code
        error_body = exc.read().decode("utf-8", errors="ignore")
        
        try:
            error_data = json.loads(error_body)
            error_msg = error_data.get("message", error_body)
        except:
            error_msg = error_body

        print_error(f"HTTP {status_code}", error_msg)
        
        # Specific troubleshooting
        print()
        if status_code == 401:
            print_warning("501", "INVALID API KEY")
            print("  - Check the API key in .env.local or environment variables")
            print("  - Make sure it starts with 're_'")
            print("  - Regenerate from https://resend.com/settings/api-keys")
        elif status_code == 422:
            print_warning("502", "VALIDATION ERROR")
            print("  - Recipient email format might be invalid")
            print("  - Domain might not be verified with Resend")
            print("  - From email might have invalid format")
            print("  Response:", error_msg)
        elif status_code == 429:
            print_warning("503", "RATE LIMITED")
            print("  - Too many requests in short time")
            print("  - Wait a moment and try again")
        
        return False
    except Exception as exc:
        print_error("Error", str(exc))
        return False


# ============================================================================
# 5. DEBUG EMAIL FUNCTION
# ============================================================================

def debug_email_send(
    to: str,
    subject: str,
    message: str,
    html_message: Optional[str] = None,
) -> dict[str, Any]:
    """
    Debug helper to test email sending with detailed logging.
    
    Args:
        to: Recipient email
        subject: Email subject
        message: Plain text message
        html_message: Optional HTML version
    
    Returns:
        Dictionary with send results and debugging info
    """
    print_section("DEBUG EMAIL SEND")
    
    result = {
        "to": to,
        "subject": subject,
        "backend": str(getattr(settings, "EMAIL_BACKEND", "")).strip(),
        "api_key_configured": bool(str(getattr(settings, "RESEND_API_KEY", "") or "").strip()),
        "from_email": str(getattr(settings, "RESEND_FROM_EMAIL", "") or "").strip() or 
                      str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip(),
        "success": False,
        "errors": [],
    }

    # Check prerequisites
    if not result["api_key_configured"]:
        result["errors"].append("RESEND_API_KEY not configured")
    if not result["from_email"]:
        result["errors"].append("From email not configured")
    
    if result["errors"]:
        print("Errors found:")
        for error in result["errors"]:
            print_error("Issue", error)
        return result

    print_status("Recipient", to)
    print_status("Subject", subject)
    print_status("Backend", result["backend"])
    print_status("From", result["from_email"])

    # Import and call the actual send function
    try:
        from app.services.core import _send_email_via_resend
        
        print()
        print("Attempting send...")
        success = _send_email_via_resend(
            subject=subject,
            message=message,
            recipient_email=to,
            html_message=html_message,
        )
        
        result["success"] = success
        if success:
            print_status("Result", "✓ Email sent successfully!")
        else:
            print_error("Result", "Email send failed - check logs above")
            result["errors"].append("_send_email_via_resend returned False")
    except Exception as exc:
        result["success"] = False
        result["errors"].append(str(exc))
        print_error("Exception", str(exc))

    return result


# ============================================================================
# 6. COMPREHENSIVE HEALTH CHECK
# ============================================================================

def run_full_health_check() -> dict[str, Any]:
    """
    Run all checks and return a comprehensive health report.
    """
    print_section("MERO TICKET EMAIL SYSTEM - FULL HEALTH CHECK")
    
    health = {
        "timestamp": str(__import__("django.utils.timezone", fromlist=["now"]).now()),
        "overall_status": "HEALTHY",
        "checks": {},
    }

    # 1. Configuration Check
    print()
    config_result = check_resend_config()
    health["checks"]["configuration"] = config_result
    if not (config_result["api_key_set"] and config_result["from_email_set"]):
        health["overall_status"] = "CRITICAL"

    # 2. Connectivity Check
    print()
    connectivity = test_resend_api_connectivity()
    health["checks"]["connectivity"] = {"success": connectivity}
    if not connectivity:
        health["overall_status"] = "CRITICAL"

    # 3. Domain Verification Check
    print()
    domain_check = check_domain_verification()
    health["checks"]["domain_verification"] = domain_check

    # Final Summary
    print_section("HEALTH CHECK SUMMARY")
    print_status("Overall Status", health["overall_status"])
    
    if health["overall_status"] == "CRITICAL":
        print()
        print_error("Action Required", "Fix the critical issues above before sending emails")
    else:
        print()
        print("✓ System appears to be configured correctly!")
        print("\nTo send a test email, run:")
        print("  python manage.py shell")
        print("  >>> from app.email_debug import send_test_email")
        print("  >>> send_test_email('your-email@example.com')")

    return health


# ============================================================================
# MANAGEMENT COMMAND INTEGRATION
# ============================================================================

def get_debug_info() -> str:
    """Get debug info as formatted string (for logging/reporting)."""
    config = check_resend_config()
    return f"""
Email Configuration:
- API Key Set: {config['api_key_set']}
- API Key Valid: {config['api_key_valid']}
- From Email Set: {config['from_email_set']}
- Issues: {', '.join(config['issues']) or 'None'}
"""
