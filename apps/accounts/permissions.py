from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission


def is_manager(user):
    return user.is_authenticated and hasattr(user, "profile") and user.profile.is_manager


def is_staff_role(user):
    return user.is_authenticated and hasattr(user, "profile") and user.profile.is_staff_role


def manager_required(view_func):
    """Decorator for function-based Django template views."""
    def wrapper(request, *args, **kwargs):
        if not is_manager(request.user):
            raise PermissionDenied("This action requires Inventory Manager privileges.")
        return view_func(request, *args, **kwargs)
    return wrapper


class IsManager(BasePermission):
    """DRF permission class — used by API viewsets from STEP 6 onward."""
    message = "This action requires Inventory Manager privileges."

    def has_permission(self, request, view):
        return is_manager(request.user)


class IsManagerOrReadOnly(BasePermission):
    """Staff can view; only managers can create/update/delete."""
    message = "This action requires Inventory Manager privileges."

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return request.user.is_authenticated
        return is_manager(request.user)
    
    
class ManagerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Class-based-view mixin — used by CreateView/UpdateView across all apps."""
    raise_exception = True

    def test_func(self):
        return is_manager(self.request.user)