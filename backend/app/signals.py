"""Signal handlers for model changes."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.db.models import Avg, Count
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Movie, Review


def _update_movie_rating(movie_id: int) -> None:
    """Recalculate and persist rating stats for a movie."""
    with transaction.atomic():
        Movie.objects.select_for_update().filter(id=movie_id).first()
        stats = Review.objects.filter(movie_id=movie_id, is_approved=True).aggregate(
            avg=Avg("rating"), count=Count("id")
        )
        avg_value = stats["avg"] or 0
        count_value = stats["count"] or 0
        try:
            avg_value = Decimal(str(avg_value)).quantize(Decimal("0.01"))
        except Exception:
            avg_value = Decimal("0.00")
        Movie.objects.filter(id=movie_id).update(
            average_rating=avg_value, review_count=count_value
        )


def _schedule_rating_update(movie_id: int) -> None:
    """Schedule rating updates after transaction commit."""
    transaction.on_commit(lambda: _update_movie_rating(movie_id))


@receiver(post_save, sender=Review)
def review_saved(sender: Any, instance: Review, **kwargs: Any) -> None:
    """Trigger rating update when a review is saved."""
    _schedule_rating_update(instance.movie_id)


@receiver(post_delete, sender=Review)
def review_deleted(sender: Any, instance: Review, **kwargs: Any) -> None:
    """Trigger rating update when a review is deleted."""
    _schedule_rating_update(instance.movie_id)
