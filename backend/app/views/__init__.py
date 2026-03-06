"""App views package exports."""

from .admin_home import (
    admin_banner_detail,
    admin_banners,
    admin_collaborator_detail,
    admin_collaborator_toggle,
    admin_collaborators,
    admin_home_slide_detail,
    admin_home_slide_toggle,
    admin_home_slides,
)
from .auth import (
    forgot_password,
    login,
    register,
    reset_password,
    update_admin_profile,
    update_profile,
    update_vendor_profile,
    verify_otp,
)
from .booking import (
    booking_cinemas,
    booking_dates,
    booking_seat_layout,
    booking_movies,
    booking_sold_seats,
    booking_times,
    create_payment_qr,
    download_ticket,
    ticket_details,
)
from .home import (
    active_banners,
    banners,
    home_collaborators,
    home_now_showing_slides,
    home_slides,
)
from .movies import (
    movie_detail,
    movie_detail_by_slug,
    movie_reviews,
    movies,
    person_detail,
    trailers,
)
from .seats import vendor_seat_layout, vendor_seat_status
from .shows import show_detail, shows
from .users import admin_user_detail, admin_users
from .vendors import list_cinemas, manage_vendors

__all__ = [
    "active_banners",
    "admin_banner_detail",
    "admin_banners",
    "admin_collaborator_detail",
    "admin_collaborator_toggle",
    "admin_collaborators",
    "admin_home_slide_detail",
    "admin_home_slide_toggle",
    "admin_home_slides",
    "admin_user_detail",
    "admin_users",
    "banners",
    "booking_cinemas",
    "booking_dates",
    "booking_seat_layout",
    "booking_movies",
    "booking_sold_seats",
    "booking_times",
    "create_payment_qr",
    "download_ticket",
    "forgot_password",
    "home_collaborators",
    "home_now_showing_slides",
    "home_slides",
    "list_cinemas",
    "login",
    "manage_vendors",
    "movie_detail",
    "movie_detail_by_slug",
    "movie_reviews",
    "movies",
    "person_detail",
    "register",
    "reset_password",
    "vendor_seat_layout",
    "vendor_seat_status",
    "show_detail",
    "shows",
    "ticket_details",
    "trailers",
    "update_admin_profile",
    "update_profile",
    "update_vendor_profile",
    "verify_otp",
]
