from rest_framework import serializers

from .models import LowStockAlert


class LowStockAlertSerializer(serializers.ModelSerializer):
    item_sku = serializers.ReadOnlyField(source="item.sku")
    dismissed_by = serializers.ReadOnlyField(source="dismissed_by.username")

    class Meta:
        model = LowStockAlert
        fields = ["id", "item", "item_sku", "dismissed", "dismissed_by", "dismissed_at", "created_at"]
        read_only_fields = fields  # entirely read-only via the generic serializer; dismiss is the only mutation, via its own action