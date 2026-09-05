from datetime import timedelta

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.db.models.functions import TruncWeek
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.permissions import is_manager
from apps.alerts.services import get_active_alerts
from apps.inventory.models import Category, Item, StockMovement
from apps.inventory.services import (
    calculate_item_stock,
    calculate_item_stock_by_location,
    get_visible_movements,
    is_below_reorder,
)
from apps.locations.models import Location
from apps.locations.services import get_accessible_locations


def _weekly_receipt_issue_series(user):
    """
    Last 8 calendar weeks (Monday-starting), Rule 7 applied via
    get_visible_movements(). Every week appears even if it has zero
    movements, so the chart's x-axis is continuous rather than skipping
    quiet weeks.
    """
    today = timezone.localdate()
    current_week_start = today - timedelta(days=today.weekday())
    week_starts = [current_week_start - timedelta(weeks=i) for i in range(7, -1, -1)]
    since = week_starts[0]

    rows = (
        get_visible_movements(user)
        .filter(
            created_at__date__gte=since,
            movement_type__in=[StockMovement.MovementType.RECEIPT, StockMovement.MovementType.ISSUE],
        )
        .annotate(week=TruncWeek("created_at"))
        .values("week", "movement_type")
        .annotate(total_qty=Sum("quantity"))
    )
    totals = {}
    for row in rows:
        week_date = row["week"].date() if hasattr(row["week"], "date") else row["week"]
        totals[(week_date, row["movement_type"])] = row["total_qty"] or 0

    labels, receipts, issues = [], [], []
    for ws in week_starts:
        labels.append(ws.strftime("%d %b"))
        receipts.append(totals.get((ws, StockMovement.MovementType.RECEIPT), 0))
        issues.append(totals.get((ws, StockMovement.MovementType.ISSUE), 0))
    return labels, receipts, issues


def _stock_by_category(active_items):
    """
    Rule 1 consequence, same trade-off documented elsewhere in this project:
    stock isn't stored, so this has to be computed per item rather than
    queried as a single aggregate. Acceptable at this project's scale.
    """
    totals = {}
    for item in active_items:
        totals[item.category.name] = totals.get(item.category.name, 0) + calculate_item_stock(item)
    labels = list(totals.keys())
    data = [totals[name] for name in labels]
    return labels, data


def _stock_by_location(user, active_items):
    """Rule 7 applied: only locations this user can see are ever charted."""
    locations = list(get_accessible_locations(user))
    totals = {loc.code: 0 for loc in locations}
    for item in active_items:
        for loc in locations:
            totals[loc.code] += calculate_item_stock_by_location(item, loc)
    labels = list(totals.keys())
    data = [totals[code] for code in labels]
    return labels, data


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        manager = is_manager(user)

        accessible_locations = get_accessible_locations(user)
        active_items = list(Item.objects.filter(is_archived=False).select_related("category"))

        context.update({
            "is_manager": manager,
            "total_items": len(active_items),
            "accessible_location_count": accessible_locations.count(),
            "accessible_locations": accessible_locations,
        })

        if manager:
            context["total_categories"] = Category.objects.count()
            context["total_locations"] = Location.objects.filter(is_active=True).count()
            context["archived_items_count"] = Item.objects.filter(is_archived=True).count()
            context["active_alert_count"] = get_active_alerts().count()

        low_stock_items = [item for item in active_items if is_below_reorder(item)]
        context["low_stock_items"] = low_stock_items[:10]
        context["low_stock_count"] = len(low_stock_items)

        context["recent_movements"] = get_visible_movements(user).order_by("-created_at")[:10]

        # --- Goal 8 additions: the two missing headline numbers ---
        context["movements_today_count"] = get_visible_movements(user).filter(
            created_at__date=timezone.localdate()
        ).count()
        context["distinct_items_this_week_count"] = (
            get_visible_movements(user)
            .filter(created_at__gte=timezone.now() - timedelta(days=7))
            .values("item_id")
            .distinct()
            .count()
        )

        # --- Goal 8 additions: the three charts ---
        category_labels, category_data = _stock_by_category(active_items)
        location_labels, location_data = _stock_by_location(user, active_items)
        week_labels, receipt_series, issue_series = _weekly_receipt_issue_series(user)

        # NOTE: pass the raw Python lists here, NOT json.dumps()'d strings.
        # The |json_script template filter does its own json.dumps() — doing
        # it here too was double-encoding everything into a JSON string of a
        # JSON string, which is why the charts previously rendered garbage
        # (Chart.js was iterating the encoded string character-by-character).
        context["chart_category_labels_json"] = category_labels
        context["chart_category_data_json"] = category_data
        context["chart_location_labels_json"] = location_labels
        context["chart_location_data_json"] = location_data
        context["chart_week_labels_json"] = week_labels
        context["chart_receipt_series_json"] = receipt_series
        context["chart_issue_series_json"] = issue_series

        return context