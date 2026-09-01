from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models

# Create your models here.

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="categories_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name
    

class Item(models.Model):
    sku = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    unit_of_measure = models.CharField(max_length=20, help_text="e.g. PCS, KG, BOX, L")
    reorder_level = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0)]
    )
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="items")
    is_archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="items_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sku"]

    def save(self, *args, **kwargs):
        self.sku = self.sku.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sku} — {self.name}"