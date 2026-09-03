from django.contrib.auth.models import User
from django.db import models


class Location(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} — {self.name}"
    


class StaffLocationAssignment(models.Model):
    staff = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="location_assignments",
        limit_choices_to={"profile__role": "STAFF"},
    )
    location = models.ForeignKey(
        Location, on_delete=models.CASCADE, related_name="staff_assignments"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("staff", "location")
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.staff.username} → {self.location.code}"