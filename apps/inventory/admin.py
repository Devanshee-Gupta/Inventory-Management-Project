from django.contrib import admin

from .models import Category, Item, StockMovement


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "created_by", "created_at")
    search_fields = ("name",)
    
@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "category", "reorder_level", "is_archived")
    list_filter = ("is_archived", "category")
    search_fields = ("sku", "name")
    
@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "movement_type", "item", "quantity", "location", "source_location", "destination_location", "recorded_by")
    list_filter = ("movement_type", "item")
    search_fields = ("item__sku", "item__name")

    def has_add_permission(self, request):
        # Movements must always go through record_stock_movement() so every
        # business rule is enforced — admin "Add" would bypass all of them.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False