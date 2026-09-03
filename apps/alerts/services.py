from django.utils import timezone

from apps.inventory.models import Item
from apps.inventory.services import is_below_reorder

from .models import LowStockAlert


def sync_low_stock_alerts():
    """
    For every non-archived item currently below reorder level, ensure an
    undismissed alert exists. See the branch-level design note for exactly
    why get_or_create(item=item, dismissed=False) is the whole mechanism.
    """
    created = []
    for item in Item.objects.filter(is_archived=False):
        if is_below_reorder(item):
            alert, was_created = LowStockAlert.objects.get_or_create(item=item, dismissed=False)
            if was_created:
                created.append(alert)
    return created


def sync_alert_for_item(item):
    """Single-item version — called right after a movement affecting one item, for immediacy."""
    if not item.is_archived and is_below_reorder(item):
        LowStockAlert.objects.get_or_create(item=item, dismissed=False)


def get_active_alerts():
    """
    'Active' = undismissed AND the item is still, right now, below reorder
    (and not archived — Rule 5's "hidden from normal screens" extends here
    too). The live re-check is what lets an alert silently leave view on
    recovery without a dismiss, yet still be ready to reappear on relapse.
    """
    candidates = LowStockAlert.objects.filter(dismissed=False).select_related("item")
    active_ids = [
        a.pk for a in candidates if not a.item.is_archived and is_below_reorder(a.item)
    ]
    return LowStockAlert.objects.filter(pk__in=active_ids).select_related("item")


def dismiss_alert(alert, dismissed_by):
    if alert.dismissed:
        raise ValueError("This alert has already been dismissed.")
    alert.dismissed = True
    alert.dismissed_by = dismissed_by
    alert.dismissed_at = timezone.now()
    alert.save()
    return alert