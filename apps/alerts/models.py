from django.conf import settings
from django.db import models


class LowStockAlert(models.Model):
    item = models.ForeignKey("inventory.Item", on_delete=models.PROTECT, related_name="low_stock_alerts")
    dismissed = models.BooleanField(default=False)
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="alerts_dismissed",
    )
    dismissed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.item.sku} · {'Dismissed' if self.dismissed else 'Active'}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            original = LowStockAlert.objects.get(pk=self.pk)
            if original.dismissed:
                raise ValueError("A dismissed alert cannot be modified further.")
            if self.item_id != original.item_id:
                raise ValueError("The item on a LowStockAlert cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Low stock alerts cannot be deleted — dismiss instead.")