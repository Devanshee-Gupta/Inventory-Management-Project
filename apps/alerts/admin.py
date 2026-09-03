from django.contrib import admin

from .models import LowStockAlert


@admin.register(LowStockAlert)
class LowStockAlertAdmin(admin.ModelAdmin):
    list_display = ("item", "dismissed", "dismissed_by", "dismissed_at", "created_at")
    list_filter = ("dismissed",)
    readonly_fields = ("item", "created_at")

    def has_add_permission(self, request):
        # Alerts are system-generated only (sync_low_stock_alerts /
        # sync_alert_for_item) — never manually created.
        return False

    def has_delete_permission(self, request, obj=None):
        return False