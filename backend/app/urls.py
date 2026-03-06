"""URL configuration for app API endpoints."""

from __future__ import annotations

from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views
from .viewsets import MovieAdminViewSet, MovieCreditViewSet, PersonViewSet, ReviewViewSet

router = DefaultRouter()
router.register(r"admin/movies", MovieAdminViewSet, basename="admin-movies")
router.register(r"people", PersonViewSet, basename="people")
router.register(r"movie-credits", MovieCreditViewSet, basename="movie-credits")
router.register(r"reviews", ReviewViewSet, basename="reviews")

urlpatterns = [
    path('auth/register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('banners/', views.banners, name='banner-list'),
    path('banners/active/', views.active_banners, name='banner-active'),
    path('admin/banners/', views.admin_banners, name='admin-banners'),
    path('admin/banners/<int:banner_id>/', views.admin_banner_detail, name='admin-banner-detail'),
    path('home/slides/', views.home_slides, name='home-slides'),
    path('home/now-showing-slides/', views.home_now_showing_slides, name='home-now-showing-slides'),
    path('home/collaborators/', views.home_collaborators, name='home-collaborators'),
    path('admin/home-slides/', views.admin_home_slides, name='admin-home-slides'),
    path('admin/home-slides/<int:slide_id>/', views.admin_home_slide_detail, name='admin-home-slide-detail'),
    path('admin/home-slides/<int:slide_id>/toggle/', views.admin_home_slide_toggle, name='admin-home-slide-toggle'),
    path('admin/collaborators/', views.admin_collaborators, name='admin-collaborators'),
    path('admin/collaborators/<int:collaborator_id>/', views.admin_collaborator_detail, name='admin-collaborator-detail'),
    path('admin/collaborators/<int:collaborator_id>/toggle/', views.admin_collaborator_toggle, name='admin-collaborator-toggle'),
    path('admin/vendors/', views.manage_vendors, name='admin-vendors'),
    path('admin/users/', views.admin_users, name='admin-users'),
    path('admin/users/<int:user_id>/', views.admin_user_detail, name='admin-user-detail'),
    path('cinemas/', views.list_cinemas, name='cinema-list'),
    path('booking/cinemas/', views.booking_cinemas, name='booking-cinemas'),
    path('booking/movies/', views.booking_movies, name='booking-movies'),
    path('booking/dates/', views.booking_dates, name='booking-dates'),
    path('booking/times/', views.booking_times, name='booking-times'),
    path('booking/seat-layout/', views.booking_seat_layout, name='booking-seat-layout'),
    path('booking/sold-seats/', views.booking_sold_seats, name='booking-sold-seats'),
    path('vendor/seat-layout/', views.vendor_seat_layout, name='vendor-seat-layout'),
    path('vendor/seat-status/', views.vendor_seat_status, name='vendor-seat-status'),
    path('movies/', views.movies, name='movie-list'),
    path('movies/<int:movie_id>/', views.movie_detail, name='movie-detail'),
    path('movies/slug/<slug:slug>/', views.movie_detail_by_slug, name='movie-detail-slug'),
    path('movies/<int:movie_id>/reviews/', views.movie_reviews, name='movie-reviews'),
    path('person/<slug:slug>/', views.person_detail, name='person-detail'),
    path('trailers/', views.trailers, name='trailer-list'),
    path('shows/', views.shows, name='show-list'),
    path('shows/<int:show_id>/', views.show_detail, name='show-detail'),
    path('auth/forgot-password/', views.forgot_password, name='forgot-password'),
    path('auth/verify-otp/', views.verify_otp, name='verify-otp'),
    path('auth/reset-password/', views.reset_password, name='reset-password'),
    path('profile/<int:user_id>/', views.update_profile, name='profile-update'),
    path('profile/admin/<int:admin_id>/', views.update_admin_profile, name='admin-profile-update'),
    path('profile/vendor/<int:vendor_id>/', views.update_vendor_profile, name='vendor-profile-update'),
    path('payment/qr/', views.create_payment_qr, name='payment-qr'),
    path('ticket/<str:reference>/download/', views.download_ticket, name='ticket-download'),
    path('ticket/<str:reference>/details/', views.ticket_details, name='ticket-details'),
]

urlpatterns += router.urls
