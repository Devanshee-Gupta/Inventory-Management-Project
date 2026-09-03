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
    

class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        RECEIPT = "RECEIPT", "Receipt"
        ISSUE = "ISSUE", "Issue"
        TRANSFER = "TRANSFER", "Transfer"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"

    class AdjustmentDirection(models.TextChoices):
        INCREASE = "INCREASE", "Increase"
        DECREASE = "DECREASE", "Decrease"

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=10, choices=MovementType.choices)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])

    location = models.ForeignKey(
        "locations.Location", on_delete=models.PROTECT, null=True, blank=True,
        related_name="movements",
    )
    source_location = models.ForeignKey(
        "locations.Location", on_delete=models.PROTECT, null=True, blank=True,
        related_name="outgoing_transfers",
    )
    destination_location = models.ForeignKey(
        "locations.Location", on_delete=models.PROTECT, null=True, blank=True,
        related_name="incoming_transfers",
    )
    adjustment_direction = models.CharField(
        max_length=10, choices=AdjustmentDirection.choices, null=True, blank=True
    )
    reason = models.TextField(blank=True)

    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="movements_recorded")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.movement_type} · {self.item.sku} · {self.quantity}"

    # ---- Rule 2: immutability enforced at the model layer, not just the view layer ----
    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError(
                "Stock movements are immutable and cannot be edited. "
                "Only new movements may be appended."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Stock movements are immutable and cannot be deleted.")


class ItemHistory(models.Model):
    class EventType(models.TextChoices):
        CREATED = "CREATED", "Created"
        UPDATED = "UPDATED", "Updated"
        NOTE = "NOTE", "Note"
        ARCHIVED = "ARCHIVED", "Archived"
        RESTORED = "RESTORED", "Restored"

    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="history")
    event_type = models.CharField(max_length=10, choices=EventType.choices)
    field_name = models.CharField(max_length=50, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)
    note = models.TextField(blank=True)
    performed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="item_history_entries")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "item histories"

    def __str__(self):
        return f"{self.item.sku} · {self.event_type} · {self.created_at:%Y-%m-%d}"

    # Rule 2's immutability principle isn't stated as applying to ItemHistory
    # explicitly, but "no edit, no delete" is the whole point of an audit
    # trail — the same model-layer guard used on StockMovement is used here.
    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Item history entries are immutable and cannot be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Item history entries are immutable and cannot be deleted.")