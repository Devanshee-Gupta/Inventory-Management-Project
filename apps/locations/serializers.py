from rest_framework import serializers
from apps.accounts.models import Profile
from .models import Location, StaffLocationAssignment


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ["id", "name", "code", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class AssignmentSerializer(serializers.ModelSerializer):
    staff_username = serializers.ReadOnlyField(source="staff.username")
    location_code = serializers.ReadOnlyField(source="location.code")

    class Meta:
        model = StaffLocationAssignment
        fields = ["id", "staff", "staff_username", "location", "location_code", "assigned_at"]
        read_only_fields = ["id", "assigned_at"]

    def validate_staff(self, value):
        if not hasattr(value, "profile") or value.profile.role != Profile.Role.STAFF:
            raise serializers.ValidationError(
                "Only Warehouse Staff users can be assigned to a location."
            )
        return value