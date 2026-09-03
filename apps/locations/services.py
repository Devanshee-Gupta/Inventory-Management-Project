from apps.accounts.permissions import is_manager
from django.db.models import Q
from .models import Location


def get_accessible_locations(user):
    """
    Rule 7: Managers see all locations. Staff see only locations
    they've been explicitly assigned to.
    """
    if is_manager(user):
        return Location.objects.all()
    return Location.objects.filter(staff_assignments__staff=user).distinct()

def filter_locations(queryset, params):
    query = (params.get("q") or "").strip()
    if query:
        queryset = queryset.filter(Q(code__icontains=query) | Q(name__icontains=query))

    status = params.get("status")
    if status == "active":
        queryset = queryset.filter(is_active=True)
    elif status == "inactive":
        queryset = queryset.filter(is_active=False)

    return queryset