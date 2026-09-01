from rest_framework import serializers

from .models import Category, Item


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