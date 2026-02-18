from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from app.models import User, Admin


class Command(BaseCommand):
    help = "Promote an existing user to system admin (Admin model)."

    def add_arguments(self, parser):
        parser.add_argument("--username", help="Username of the user")
        parser.add_argument("--email", help="Email of the user")
        parser.add_argument("--phone", help="Phone number of the user")
        parser.add_argument("--full-name", dest="full_name", help="Override full name")
        parser.add_argument(
            "--deactivate",
            action="store_true",
            help="Create/update admin as inactive",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without saving",
        )

    def handle(self, *args, **options):
        username = options.get("username")
        email = options.get("email")
        phone = options.get("phone")
        full_name_override = options.get("full_name")
        deactivate = options.get("deactivate")
        dry_run = options.get("dry_run")

        if not any([username, email, phone]):
            raise CommandError("Provide --username, --email, or --phone to identify the user.")

        user_q = Q()
        if username:
            user_q |= Q(username__iexact=username)
        if email:
            user_q |= Q(email__iexact=email)
        if phone:
            user_q |= Q(phone_number=phone)

        user = User.objects.filter(user_q).first()
        if not user:
            raise CommandError("User not found with the provided identifier(s).")

        full_name = full_name_override or " ".join(
            part for part in [user.first_name, user.middle_name, user.last_name] if part
        ).strip()

        admin_q = Q(email__iexact=user.email)
        if user.username:
            admin_q |= Q(username__iexact=user.username)
        if user.phone_number:
            admin_q |= Q(phone_number=user.phone_number)

        admin = Admin.objects.filter(admin_q).first()
        is_active = not deactivate

        action = "update" if admin else "create"
        summary = (
            f"Will {action} admin for user '{user.username or user.email}' "
            f"(email={user.email}, phone={user.phone_number})."
        )
        self.stdout.write(summary)

        if dry_run:
            return

        with transaction.atomic():
            if admin:
                admin.email = user.email
                admin.username = user.username
                admin.phone_number = user.phone_number
                admin.full_name = full_name or admin.full_name
                # Reuse user's hashed password to allow the same login credentials.
                admin.password = user.password
                admin.is_active = is_active
                admin.save()
            else:
                admin = Admin(
                    email=user.email,
                    username=user.username,
                    phone_number=user.phone_number,
                    full_name=full_name or None,
                    password=user.password,
                    is_active=is_active,
                )
                admin.save()

        self.stdout.write(self.style.SUCCESS("Admin promotion complete."))
