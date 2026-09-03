from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.accounts.permissions import is_manager
from apps.inventory.models import Category, Item
from apps.inventory.services import calculate_item_stock, get_visible_movements, is_below_reorder
from apps.locations.models import Location
from apps.locations.services import get_accessible_locations


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        manager = is_manager(user)

        accessible_locations = get_accessible_locations(user)
        active_items = Item.objects.filter(is_archived=False).select_related("category")

        context.update({
            "is_manager": manager,
            "total_items": active_items.count(),
            "accessible_location_count": accessible_locations.count(),
            "accessible_locations": accessible_locations,
        })

        if manager:
            context["total_categories"] = Category.objects.count()
            context["total_locations"] = Location.objects.filter(is_active=True).count()
            context["archived_items_count"] = Item.objects.filter(is_archived=True).count()

        # Rule 1 consequence, same trade-off documented in STEP 9: no stored
        # stock column means this has to be computed per item, live. Fine at
        # this project's scale; would need revisiting at a much larger catalog.
        low_stock_items = [item for item in active_items if is_below_reorder(item)]
        context["low_stock_items"] = low_stock_items[:10]
        context["low_stock_count"] = len(low_stock_items)

        # Rule 7 applies to the recent-activity feed exactly like it does
        # on the full movement history screen — same shared function.
        context["recent_movements"] = get_visible_movements(user).order_by("-created_at")[:10]

        return context