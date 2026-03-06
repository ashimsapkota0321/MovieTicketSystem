"""Application configuration for the app module."""

from __future__ import annotations

from django.apps import AppConfig


class AppConfig(AppConfig):
    """Django app configuration."""

    name = "app"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        """Register signal handlers."""
        from . import signals  # noqa: F401
