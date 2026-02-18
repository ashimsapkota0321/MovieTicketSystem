from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    message = "Super admin access required."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "is_staff", False)
            and getattr(user, "is_superuser", False)
        )

