"""Django admin registrations and display helpers."""

from __future__ import annotations

from django.contrib import admin
from django.forms.models import BaseInlineFormSet
from django.utils.html import format_html
from .models import (
    User,
    Admin,
    Movie,
    Banner,
    HomeSlide,
    CollabDetails,
    Collaborator,
    MovieGenre,
    MovieMovieGenre,
    Person,
    MovieCredit,
    Review,
)

SMALL_IMAGE_HEIGHT = 32
MEDIUM_IMAGE_HEIGHT = 40
BANNER_PREVIEW_HEIGHT = 50


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "first_name", "last_name", "is_active", "date_joined")
    search_fields = ("email", "first_name", "last_name", "phone_number")
    list_filter = ("is_active",)


@admin.register(Admin)
class AdminUserAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "full_name", "is_active", "date_joined")
    search_fields = ("email", "full_name", "username")
    list_filter = ("is_active",)


@admin.register(Movie)
class MovieAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "status",
        "release_date",
        "average_rating",
        "review_count",
        "is_active",
    )
    search_fields = ("title", "slug", "genre")
    list_filter = ("status", "is_active")
    prepopulated_fields = {"slug": ("title",)}
    inlines = []


class MovieGenreInline(admin.TabularInline):
    model = MovieMovieGenre
    extra = 1
    autocomplete_fields = ["genre"]


class BaseMovieCreditInlineFormSet(BaseInlineFormSet):
    role_type = None

    def save_new(self, form, commit=True):
        """Force the credit role type when creating new credits."""
        obj = super().save_new(form, commit=False)
        obj.role_type = self.role_type
        if commit:
            obj.save()
            form.save_m2m()
        return obj

    def save_existing(self, form, instance, commit=True):
        """Force the credit role type when updating existing credits."""
        instance.role_type = self.role_type
        return super().save_existing(form, instance, commit=commit)


class MovieCreditInline(admin.TabularInline):
    model = MovieCredit
    extra = 1
    autocomplete_fields = ["person"]
    fields = ("person", "character_name", "job_title", "position")
    formset = BaseMovieCreditInlineFormSet
    role_type = None

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self.role_type:
            qs = qs.filter(role_type=self.role_type)
        return qs

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.role_type = self.role_type
        return formset


class CastInline(MovieCreditInline):
    verbose_name_plural = "Cast"
    role_type = MovieCredit.ROLE_CAST


class CrewInline(MovieCreditInline):
    verbose_name_plural = "Crew"
    role_type = MovieCredit.ROLE_CREW


MovieAdmin.inlines = [MovieGenreInline, CastInline, CrewInline]


@admin.register(MovieGenre)
class MovieGenreAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "slug", "is_active")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    list_filter = ("is_active",)


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("id", "full_name", "nationality", "photo_preview")
    search_fields = ("full_name", "slug")
    prepopulated_fields = {"slug": ("full_name",)}

    def photo_preview(self, obj: Person) -> str:
        """Render a tiny photo thumbnail for the admin list."""
        if obj.photo:
            return format_html(
                '<img src="{}" style="height:{}px;" />', obj.photo.url, MEDIUM_IMAGE_HEIGHT
            )
        if obj.photo_url:
            return format_html(
                '<img src="{}" style="height:{}px;" />', obj.photo_url, MEDIUM_IMAGE_HEIGHT
            )
        return "-"

    photo_preview.short_description = "Photo"


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "movie", "user", "rating", "is_approved", "created_at")
    list_filter = ("is_approved", "rating")
    search_fields = ("movie__title", "user__email", "user__first_name", "user__last_name")


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "banner_type",
        "movie",
        "is_active",
        "created_at",
        "image_preview",
    )
    list_filter = ("banner_type", "is_active")
    search_fields = ("movie__title",)
    ordering = ("-created_at",)
    readonly_fields = ("image_preview",)

    def image_preview(self, obj: Banner) -> str:
        """Render a banner thumbnail for the admin list."""
        if not obj.image:
            return "-"
        return format_html(
            '<img src="{}" style="height:{}px;" />', obj.image.url, BANNER_PREVIEW_HEIGHT
        )

    image_preview.short_description = "Image"


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
        """Show collab details only for COLLAB slides."""
        if obj is None or obj.slide_type != HomeSlide.SLIDE_COLLAB:
            return []
        return super().get_inline_instances(request, obj)


@admin.register(Collaborator)
class CollaboratorAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active", "sort_order", "logo_preview")
    list_filter = ("is_active",)
    ordering = ("sort_order", "name")

    def logo_preview(self, obj: Collaborator) -> str:
        """Render a small collaborator logo thumbnail."""
        if not obj.logo:
            return "-"
        return format_html(
            '<img src="{}" style="height:{}px;" />', obj.logo.url, SMALL_IMAGE_HEIGHT
        )

    logo_preview.short_description = "Logo"


@admin.register(CollabDetails)
class CollabDetailsAdmin(admin.ModelAdmin):
    list_display = ("id", "partner_name", "slide")
    search_fields = ("partner_name",)
