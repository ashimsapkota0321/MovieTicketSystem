"""Booking flow and ticket generation API views."""

from __future__ import annotations

from typing import Any, Optional

from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .. import selectors, services
from ..utils import coalesce, parse_date


def _coerce_int(value: Any) -> Optional[int]:
    """Safely coerce a value into an int or return None."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@api_view(["GET"])
def booking_cinemas(request: Any):
    """Return cinemas for booking dropdowns, optionally filtered by movie."""
    movie_id = _coerce_int(
        coalesce(request.query_params, "movie_id", "movieId", "movie")
    )
    if movie_id:
        vendors = selectors.list_vendors_for_movie(movie_id)
    else:
        vendors = selectors.list_cinema_vendors()
    payload = services.build_cinemas_payload(vendors, request)
    return Response({"cinemas": payload}, status=status.HTTP_200_OK)


@api_view(["GET"])
def booking_movies(request: Any):
    """Return movies for booking dropdowns, optionally filtered by cinema."""
    cinema_id = _coerce_int(
        coalesce(
            request.query_params,
            "cinema_id",
            "cinemaId",
            "vendor_id",
            "vendorId",
        )
    )
    if cinema_id:
        movies = selectors.list_movies_for_vendor(cinema_id)
    else:
        movies = selectors.list_movies_with_shows()
    payload = [selectors.build_movie_select_payload(movie) for movie in movies]
    return Response({"movies": payload}, status=status.HTTP_200_OK)


@api_view(["GET"])
def booking_dates(request: Any):
    """Return available show dates for a cinema + movie selection."""
    cinema_id = _coerce_int(
        coalesce(
            request.query_params,
            "cinema_id",
            "cinemaId",
            "vendor_id",
            "vendorId",
        )
    )
    movie_id = _coerce_int(
        coalesce(request.query_params, "movie_id", "movieId", "movie")
    )
    if not cinema_id or not movie_id:
        return Response({"dates": []}, status=status.HTTP_200_OK)

    dates = selectors.list_show_dates_for_vendor_movie(cinema_id, movie_id)
    payload = [date.isoformat() for date in dates if date]
    return Response({"dates": payload}, status=status.HTTP_200_OK)


@api_view(["GET"])
def booking_times(request: Any):
    """Return available show times for a cinema + movie + date selection."""
    cinema_id = _coerce_int(
        coalesce(
            request.query_params,
            "cinema_id",
            "cinemaId",
            "vendor_id",
            "vendorId",
        )
    )
    movie_id = _coerce_int(
        coalesce(request.query_params, "movie_id", "movieId", "movie")
    )
    show_date = parse_date(
        coalesce(request.query_params, "date", "show_date", "showDate")
    )
    if not cinema_id or not movie_id or not show_date:
        return Response({"times": []}, status=status.HTTP_200_OK)

    times = selectors.list_show_times_for_vendor_movie_date(
        cinema_id, movie_id, show_date
    )
    payload = [time.strftime("%H:%M") for time in times if time]
    return Response({"times": payload}, status=status.HTTP_200_OK)


@api_view(["GET"])
def booking_sold_seats(request: Any):
    """Return sold seat labels for a selected show context."""
    query_payload = {
        key: request.query_params.get(key)
        for key in request.query_params.keys()
    }
    payload, status_code = services.list_sold_seats_for_context(query_payload)
    return Response(payload, status=status_code)


@api_view(["GET"])
def booking_seat_layout(request: Any):
    """Return seat layout + statuses for customer booking page."""
    query_payload = {
        key: request.query_params.get(key)
        for key in request.query_params.keys()
    }
    payload, status_code = services.list_booking_seat_layout(query_payload)
    return Response(payload, status=status_code)


@api_view(["POST"])
def create_payment_qr(request: Any):
    """Create a payment QR code and ticket details."""
    payload, status_code = services.create_payment_qr(request)
    return Response(payload, status=status_code)


def download_ticket(request: Any, reference: str):
    """Download a ticket image by reference."""
    content = services.build_ticket_download(reference)
    if content is None:
        return HttpResponse("Ticket not found", status=404)

    response = HttpResponse(content, content_type="image/png")
    response["Content-Disposition"] = f'attachment; filename="ticket-{reference}.png"'
    return response


def ticket_details(request: Any, reference: str):
    """Render ticket details HTML by reference."""
    html = services.build_ticket_details_html(reference)
    if html is None:
        return HttpResponse("Ticket not found", status=404)
    return HttpResponse(html, content_type="text/html")
