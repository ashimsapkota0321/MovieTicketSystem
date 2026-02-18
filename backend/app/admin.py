from django.contrib import admin
from django.utils.html import format_html
from .models import (
    User,
    Admin,
    Movie,
    HomeSlide,
    CollabDetails,
    Collaborator,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "first_name", "last_name", "date_joined")
    search_fields = ("email", "first_name", "last_name", "phone_number")


@admin.register(Admin)
class AdminUserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "full_name", "is_active", "date_joined")
    search_fields = ("email", "full_name", "username")
    list_filter = ("is_active",)


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "genre", "release_date", "status")
    search_fields = ("title", "genre")
    list_filter = ("status",)


class CollabDetailsInline(admin.StackedInline):
    model = CollabDetails
    extra = 0
    max_num = 1


@admin.register(HomeSlide)
class HomeSlideAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "slide_type",
        "movie",
        "badge_text",
        "cta_type",
        "is_active",
        "sort_order",
    )
    list_filter = ("slide_type", "is_active", "cta_type")
    ordering = ("sort_order",)
    inlines = [CollabDetailsInline]

    def get_inline_instances(self, request, obj=None):
        if obj is None or obj.slide_type != HomeSlide.SLIDE_COLLAB:
            return []
        return super().get_inline_instances(request, obj)


@admin.register(Collaborator)
class CollaboratorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active", "sort_order", "logo_preview")
    list_filter = ("is_active",)
    ordering = ("sort_order", "name")

    def logo_preview(self, obj):
        if not obj.logo:
            return "-"
        return format_html('<img src="{}" style="height:32px;" />', obj.logo.url)

    logo_preview.short_description = "Logo"


@admin.register(CollabDetails)
class CollabDetailsAdmin(admin.ModelAdmin):
    list_display = ("id", "partner_name", "slide")
    search_fields = ("partner_name",)
