from django.contrib import admin

from .models import Location, StaffLocationAssignment


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "created_at")
    search_fields = ("code", "name")
    list_filter = ("is_active",)
    

@admin.register(StaffLocationAssignment)
class StaffLocationAssignmentAdmin(admin.ModelAdmin):
    list_display = ("staff", "location", "assigned_at")
    list_filter = ("location",)
    search_fields = ("staff__username", "location__code")