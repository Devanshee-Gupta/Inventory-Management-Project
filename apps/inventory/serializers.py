from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError, PermissionDenied
from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
from .models import Category, Item, StockMovement
from .services import record_stock_movement


class CategorySerializer(serializers.ModelSerializer):
    created_by = serializers.ReadOnlyField(source="created_by.username")

    class Meta:
        model = Category
        fields = ["id", "name", "description", "created_by", "created_at", "updated_at"]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


class ItemSerializer(serializers.ModelSerializer):
    category_name = serializers.ReadOnlyField(source="category.name")
    created_by = serializers.ReadOnlyField(source="created_by.username")

    class Meta:
        model = Item
        fields = [
            "id", "sku", "name", "description", "unit_of_measure", "reorder_level",
            "category", "category_name", "is_archived", "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "is_archived", "created_by", "created_at", "updated_at"]
        

class StockMovementSerializer(serializers.ModelSerializer):
    recorded_by = serializers.ReadOnlyField(source="recorded_by.username")

    class Meta:
        model = StockMovement
        fields = [
            "id", "item", "movement_type", "quantity",
            "location", "source_location", "destination_location",
            "adjustment_direction", "reason", "recorded_by", "created_at",
        ]
        read_only_fields = ["id", "recorded_by", "created_at"]

    def create(self, validated_data):
        request = self.context["request"]
        try:
            return record_stock_movement(recorded_by=request.user, **validated_data)
        except DjangoValidationError as exc:
            detail = exc.message if hasattr(exc, "message") else exc.messages
            raise serializers.ValidationError(detail)
        except PermissionDenied as exc:
            raise DRFPermissionDenied(str(exc))