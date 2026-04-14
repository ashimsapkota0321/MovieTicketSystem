"""
Email testing utilities and examples for Django shell testing.

Usage in Django shell:

    python manage.py shell
    >>> from app.email_test_fixtures import *
    
    # Run specific test
    >>> test_basic_email_send()
    >>> test_html_email()
    >>> test_batch_emails()
    >>> run_all_tests()
"""

import logging
from typing import Optional, Dict, Any
from django.conf import settings
from app.services.core import _send_notification_email

logger = logging.getLogger(__name__)


def log_test(test_name: str, result: bool, details: Optional[str] = None):
    """Log test result."""
    status = "✓ PASS" if result else "✗ FAIL"
    print(f"\n{status}: {test_name}")
    if details:
        print(f"  Details: {details}")


# =============================================================================
# TEST 1: BASIC EMAIL SEND
# =============================================================================

def test_basic_email_send(recipient: str = "test@example.com") -> bool:
    """
    Test 1: Send a basic plain-text email.
    
    Usage:
        result = test_basic_email_send("your-email@example.com")
        print(result)
    """
    print("\n" + "=" * 60)
    print("TEST 1: Basic Email Send")
    print("=" * 60)
    
    try:
        subject = "Test Email - Plain Text"
        message = "This is a test email from Mero Ticket."
        
        print(f"Sending to: {recipient}")
        print(f"Subject: {subject}")
        
        success = _send_notification_email(
            subject=subject,
            message=message,
            recipient_email=recipient,
        )
        
        log_test("Basic Email Send", success, f"Recipient: {recipient}")
        return success
    except Exception as e:
        log_test("Basic Email Send", False, str(e))
        return False


# =============================================================================
# TEST 2: HTML EMAIL
# =============================================================================

def test_html_email(recipient: str = "test@example.com") -> bool:
    """
    Test 2: Send an email with HTML formatting.
    """
    print("\n" + "=" * 60)
    print("TEST 2: HTML Email")
    print("=" * 60)
    
    try:
        subject = "Test Email - HTML"
        message = "This is a test email with HTML formatting."
        html_message = """
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #111827; color: white; padding: 20px; text-align: center;">
                <h1>Mero Ticket Email Test</h1>
            </div>
            <div style="padding: 20px; background: #f9fafb;">
                <h2>Welcome!</h2>
                <p>This is an HTML formatted test email.</p>
                <ul>
                    <li>✓ HTML Support</li>
                    <li>✓ Styling Applied</li>
                    <li>✓ Professional Appearance</li>
                </ul>
                <p style="margin-top: 20px;">
                    <a href="https://meroticket.local" style="background: #0f172a; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px;">
                        Visit Mero Ticket
                    </a>
                </p>
            </div>
        </div>
        """
        
        print(f"Sending to: {recipient}")
        print(f"Subject: {subject}")
        
        success = _send_notification_email(
            subject=subject,
            message=message,
            recipient_email=recipient,
            html_message=html_message,
        )
        
        log_test("HTML Email", success, f"Recipient: {recipient}")
        return success
    except Exception as e:
        log_test("HTML Email", False, str(e))
        return False


# =============================================================================
# TEST 3: MULTIPLE RECIPIENTS (BATCH)
# =============================================================================

def test_batch_emails(recipients: Optional[list] = None) -> Dict[str, bool]:
    """
    Test 3: Send emails to multiple recipients.
    
    Note: SMTP backends send one message per recipient in this loop.
    
    Usage:
        results = test_batch_emails(["email1@test.com", "email2@test.com"])
    """
    print("\n" + "=" * 60)
    print("TEST 3: Batch Email Send")
    print("=" * 60)
    
    if not recipients:
        recipients = [
            "test1@example.com",
            "test2@example.com",
        ]
    
    results = {}
    for i, recipient in enumerate(recipients, 1):
        try:
            subject = f"Batch Test Email #{i}"
            message = f"Batch test email to recipient {i}"
            
            print(f"\n[{i}/{len(recipients)}] Sending to: {recipient}")
            
            success = _send_notification_email(
                subject=subject,
                message=message,
                recipient_email=recipient,
            )
            
            results[recipient] = success
            status = "✓ SENT" if success else "✗ FAILED"
            print(f"  {status}")
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            results[recipient] = False
    
    # Summary
    successful = sum(1 for v in results.values() if v)
    print(f"\n{successful}/{len(recipients)} emails sent successfully")
    
    return results


# =============================================================================
# TEST 4: OTP/CODE EMAIL
# =============================================================================

def test_otp_email(recipient: str = "test@example.com") -> bool:
    """
    Test 4: Send an OTP code email (like password reset).
    """
    print("\n" + "=" * 60)
    print("TEST 4: OTP Email")
    print("=" * 60)
    
    try:
        otp = "123456"
        subject = "Your Mero Ticket Password Reset Code"
        message = f"Your password reset code is: {otp}\n\nThis code is valid for 10 minutes."
        
        html_message = f"""
        <div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto;
                    border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden;">
            <div style="background: #111827; color: white; padding: 18px 20px; 
                        font-size: 18px; font-weight: bold;">
                Mero Ticket - Password Reset
            </div>
            <div style="padding: 20px; color: #111827;">
                <p style="margin: 0 0 12px 0; font-size: 14px;">
                    Use the OTP below to reset your password:
                </p>
                <div style="font-size: 32px; letter-spacing: 8px; font-weight: bold;
                            color: #0f172a; margin: 8px 0 16px 0;">
                    {otp}
                </div>
                <p style="margin: 0 0 8px 0; font-size: 13px; color: #4b5563;">
                    This OTP is valid for 10 minutes.
                </p>
                <p style="margin: 0; font-size: 13px; color: #4b5563;">
                    If you did not request this, please ignore this email.
                </p>
            </div>
        </div>
        """
        
        print(f"Sending to: {recipient}")
        print(f"Subject: {subject}")
        print(f"OTP Code: {otp}")
        
        success = _send_notification_email(
            subject=subject,
            message=message,
            recipient_email=recipient,
            html_message=html_message,
        )
        
        log_test("OTP Email", success, f"OTP: {otp}")
        return success
    except Exception as e:
        log_test("OTP Email", False, str(e))
        return False


# =============================================================================
# TEST 5: BOOKING CONFIRMATION EMAIL
# =============================================================================

def test_booking_confirmation_email(recipient: str = "test@example.com") -> bool:
    """
    Test 5: Send a booking confirmation email (realistic example).
    """
    print("\n" + "=" * 60)
    print("TEST 5: Booking Confirmation Email")
    print("=" * 60)
    
    try:
        # Sample booking data
        booking_data = {
            "id": 12345,
            "movie_title": "Avengers: Endgame",
            "cinema": "Cineplex Downtown",
            "date": "2026-04-15",
            "time": "19:30",
            "seats": "A1, A2, A3",
            "total_amount": "150.00",
            "booking_reference": "MTK-2026-001234",
        }
        
        subject = f"Booking Confirmed - {booking_data['booking_reference']}"
        message = f"""
Booking Confirmation
====================

Reference: {booking_data['booking_reference']}
Movie: {booking_data['movie_title']}
Cinema: {booking_data['cinema']}
Date: {booking_data['date']}
Time: {booking_data['time']}
Seats: {booking_data['seats']}
Amount: Rs. {booking_data['total_amount']}

Thank you for booking with Mero Ticket!
        """
        
        html_message = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #111827; color: white; padding: 20px; text-align: center;">
                <h1>✓ Booking Confirmed</h1>
            </div>
            <div style="padding: 20px; background: #f9fafb;">
                <div style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                    <h3 style="margin-top: 0;">Booking Reference</h3>
                    <p style="font-size: 24px; font-weight: bold; color: #0f172a;">
                        {booking_data['booking_reference']}
                    </p>
                </div>
                
                <div style="background: white; padding: 15px; border-radius: 8px;">
                    <h3 style="margin-top: 0;">Booking Details</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr style="border-bottom: 1px solid #e5e7eb;">
                            <td style="padding: 8px; font-weight: bold;">Movie</td>
                            <td style="padding: 8px;">{booking_data['movie_title']}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #e5e7eb;">
                            <td style="padding: 8px; font-weight: bold;">Cinema</td>
                            <td style="padding: 8px;">{booking_data['cinema']}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #e5e7eb;">
                            <td style="padding: 8px; font-weight: bold;">Date</td>
                            <td style="padding: 8px;">{booking_data['date']}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #e5e7eb;">
                            <td style="padding: 8px; font-weight: bold;">Time</td>
                            <td style="padding: 8px;">{booking_data['time']}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #e5e7eb;">
                            <td style="padding: 8px; font-weight: bold;">Seats</td>
                            <td style="padding: 8px;">{booking_data['seats']}</td>
                        </tr>
                        <tr style="background: #f3f4f6;">
                            <td style="padding: 8px; font-weight: bold;">Total Amount</td>
                            <td style="padding: 8px; font-weight: bold;">Rs. {booking_data['total_amount']}</td>
                        </tr>
                    </table>
                </div>
            </div>
        </div>
        """
        
        print(f"Sending to: {recipient}")
        print(f"Subject: {subject}")
        print(f"Booking ID: {booking_data['id']}")
        
        success = _send_notification_email(
            subject=subject,
            message=message,
            recipient_email=recipient,
            html_message=html_message,
        )
        
        log_test("Booking Confirmation", success, f"Booking: {booking_data['booking_reference']}")
        return success
    except Exception as e:
        log_test("Booking Confirmation", False, str(e))
        return False


# =============================================================================
# TEST 6: NEWSLETTER/BULK EMAIL
# =============================================================================

def test_newsletter_email(recipient: str = "test@example.com") -> bool:
    """
    Test 6: Send a newsletter-style email.
    """
    print("\n" + "=" * 60)
    print("TEST 6: Newsletter Email")
    print("=" * 60)
    
    try:
        subject = "Mero Ticket Weekly Newsletter - New Movies This Week!"
        message = """
Welcome to Mero Ticket Weekly!

This week's highlights:

1. Deadpool & Wolverine (Action) - Now showing
2. Inside Out 2 (Comedy) - Coming Friday
3. The Lion King (Family) - Weekend special

Check out our latest deals: 20% off group bookings!

Unsubscribe: Click here
        """
        
        html_message = """
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #111827 0%, #1f2937 100%); 
                        color: white; padding: 30px; text-align: center;">
                <h1 style="margin: 0;">Mero Ticket Weekly</h1>
                <p style="margin: 0; opacity: 0.9;">New Movies This Week!</p>
            </div>
            
            <div style="padding: 20px;">
                <h2>This Week's Highlights</h2>
                
                <div style="background: #f9fafb; padding: 15px; margin: 10px 0; border-radius: 8px;">
                    <h3 style="margin-top: 0;">🎬 Deadpool & Wolverine</h3>
                    <p>Action | Now Showing</p>
                </div>
                
                <div style="background: #f9fafb; padding: 15px; margin: 10px 0; border-radius: 8px;">
                    <h3 style="margin-top: 0;">😄 Inside Out 2</h3>
                    <p>Comedy | Coming Friday</p>
                </div>
                
                <div style="background: #f9fafb; padding: 15px; margin: 10px 0; border-radius: 8px;">
                    <h3 style="margin-top: 0;">👑 The Lion King</h3>
                    <p>Family | Weekend Special</p>
                </div>
                
                <div style="background: #FEF3C7; padding: 15px; margin: 20px 0; border-radius: 8px; 
                            border-left: 4px solid #F59E0B;">
                    <strong>Special Offer!</strong>
                    <p style="margin: 5px 0 0 0;">20% off group bookings (4+ tickets)</p>
                </div>
            </div>
        </div>
        """
        
        print(f"Sending to: {recipient}")
        print(f"Subject: {subject}")
        
        success = _send_notification_email(
            subject=subject,
            message=message,
            recipient_email=recipient,
            html_message=html_message,
        )
        
        log_test("Newsletter Email", success)
        return success
    except Exception as e:
        log_test("Newsletter Email", False, str(e))
        return False


# =============================================================================
# TEST 7: ERROR HANDLING
# =============================================================================

def test_error_handling() -> bool:
    """
    Test 7: Test error handling with invalid email.
    """
    print("\n" + "=" * 60)
    print("TEST 7: Error Handling")
    print("=" * 60)
    
    try:
        print("Attempting to send to invalid email...")
        
        success = _send_notification_email(
            subject="Test",
            message="Test",
            recipient_email="invalid-email",  # Invalid format
        )
        
        # Should fail gracefully
        log_test("Error Handling", not success, "Correctly rejected invalid email")
        return not success
    except Exception as e:
        log_test("Error Handling", False, f"Exception: {e}")
        return False


# =============================================================================
# COMPREHENSIVE TEST SUITE
# =============================================================================

def run_all_tests(recipient: str = "test@example.com") -> Dict[str, bool]:
    """
    Run all email tests.
    
    Usage:
        results = run_all_tests("your-email@example.com")
        for test_name, passed in results.items():
            print(f"{test_name}: {'PASS' if passed else 'FAIL'}")
    """
    print("\n" + "=" * 60)
    print("MERO TICKET EMAIL TEST SUITE")
    print("=" * 60)
    
    results = {
        "test_basic_email_send": test_basic_email_send(recipient),
        "test_html_email": test_html_email(recipient),
        "test_batch_emails": bool(test_batch_emails()),
        "test_otp_email": test_otp_email(recipient),
        "test_booking_confirmation": test_booking_confirmation_email(recipient),
        "test_newsletter_email": test_newsletter_email(recipient),
        "test_error_handling": test_error_handling(),
    }
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓" if result else "✗"
        print(f"{status} {test_name}")
    
    print()
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ ALL TESTS PASSED! Email system is working correctly.")
    else:
        print(f"\n✗ {total - passed} test(s) failed. Review errors above.")
    
    return results


# =============================================================================
# QUICK TEST
# =============================================================================

def quick_test(email: Optional[str] = None) -> bool:
    """
    Quick test with single email.
    
    Usage:
        quick_test()  # Uses test@example.com
        quick_test("your@email.com")
    """
    if not email:
        email = "test@example.com"
        print(f"Using default test email: {email}")
        print("To use your email, call: quick_test('your@email.com')")
    
    return test_basic_email_send(email)
