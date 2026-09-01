from apps.accounts.permissions import is_manager

from .models import Location


def get_accessible_locations(user):
    """
    Rule 7: Managers see all locations. Staff see only locations
    they've been explicitly assigned to.
    """
    if is_manager(user):
        return Location.objects.all()
    return Location.objects.filter(staff_assignments__staff=user).distinct()