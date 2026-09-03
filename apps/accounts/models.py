from django.db import models

# Create your models here.
from django.contrib.auth.models import User
from django.db import models


class Profile(models.Model):
    class Role(models.TextChoices):
        MANAGER = "MANAGER", "Inventory Manager"
        STAFF = "STAFF", "Warehouse Staff"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STAFF)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_staff_role(self):
        return self.role == self.Role.STAFF