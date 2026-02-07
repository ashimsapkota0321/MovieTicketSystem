from django.urls import path
from . import views

urlpatterns = [
    path('auth/register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('auth/forgot-password/', views.forgot_password, name='forgot-password'),
    path('auth/verify-otp/', views.verify_otp, name='verify-otp'),
    path('auth/reset-password/', views.reset_password, name='reset-password'),
    path('auth/debug-otp/', views.debug_get_otp, name='debug-otp'),
]
