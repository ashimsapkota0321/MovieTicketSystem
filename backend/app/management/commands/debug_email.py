"""
Django management command to debug and test email sending.

Usage:
    python manage.py debug_email check              # Check configuration
    python manage.py debug_email connectivity       # Test API connectivity
    python manage.py debug_email domain             # Check domain verification  
    python manage.py debug_email test --email your@email.com  # Send test email
    python manage.py debug_email health             # Full health check
"""

from django.core.management.base import BaseCommand, CommandError
from app.email_debug import (
    check_resend_config,
    test_resend_api_connectivity,
    check_domain_verification,
    send_test_email,
    run_full_health_check,
    print_section,
)


class Command(BaseCommand):
    help = "Debug and test Resend email configuration"

    def add_arguments(self, parser):
        parser.add_argument(
            "command",
            nargs="?",
            default="health",
            type=str,
            choices=["check", "connectivity", "domain", "test", "health", "config"],
            help="Debug command to run",
        )
        parser.add_argument(
            "--email",
            "-e",
            type=str,
            help="Email address for test (required for 'test' command)",
        )

    def handle(self, *args, **options):
        command = options["command"]

        try:
            if command == "check" or command == "config":
                check_resend_config()
            elif command == "connectivity":
                test_resend_api_connectivity()
            elif command == "domain":
                check_domain_verification()
            elif command == "test":
                email = options.get("email")
                if not email:
                    raise CommandError("--email is required for test command")
                success = send_test_email(email)
                if not success:
                    raise CommandError("Email send failed - check output above")
            elif command == "health":
                run_full_health_check()
        except Exception as e:
            raise CommandError(str(e))

        self.stdout.write(self.style.SUCCESS("\n✓ Check complete\n"))
