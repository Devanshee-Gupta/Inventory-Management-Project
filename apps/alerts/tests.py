from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile
from apps.inventory.models import Category, Item, StockMovement
from apps.inventory.services import record_stock_movement
from apps.locations.models import Location

from .models import LowStockAlert
from .services import dismiss_alert, get_active_alerts, sync_low_stock_alerts


class LowStockAlertImmutabilityTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", reorder_level=10, category=self.category, created_by=self.manager)

    def test_alert_cannot_be_deleted(self):
        alert = LowStockAlert.objects.create(item=self.item)
        with self.assertRaises(ValueError):
            alert.delete()

    def test_dismissed_alert_cannot_be_modified_further(self):
        alert = LowStockAlert.objects.create(item=self.item)
        dismiss_alert(alert, self.manager)
        alert.dismissed_by = self.manager  # touch it again after already dismissed
        with self.assertRaises(ValueError):
            alert.save()

    def test_double_dismiss_rejected(self):
        alert = LowStockAlert.objects.create(item=self.item)
        dismiss_alert(alert, self.manager)
        with self.assertRaises(ValueError):
            dismiss_alert(alert, self.manager)


class LowStockAlertLifecycleTests(TestCase):
    """The core state-machine behavior described in the branch design note."""

    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", reorder_level=10, category=self.category, created_by=self.manager)
        self.wh = Location.objects.create(name="Main Warehouse", code="WH01")

    def test_alert_created_when_stock_drops_below_reorder(self):
        # 0 stock, reorder_level 10 -> already below at creation time
        sync_low_stock_alerts()
        self.assertEqual(LowStockAlert.objects.filter(item=self.item, dismissed=False).count(), 1)

    def test_no_duplicate_alert_while_continuously_low(self):
        sync_low_stock_alerts()
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=3, location=self.wh, recorded_by=self.manager)  # still below 10
        sync_low_stock_alerts()
        self.assertEqual(LowStockAlert.objects.filter(item=self.item).count(), 1)

    def test_alert_leaves_active_view_on_recovery_without_dismiss(self):
        sync_low_stock_alerts()
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=50, location=self.wh, recorded_by=self.manager)  # now above 10
        active = get_active_alerts()
        self.assertNotIn(self.item.pk, [a.item.pk for a in active])
        # underlying row is untouched, not dismissed
        self.assertFalse(LowStockAlert.objects.get(item=self.item).dismissed)

    def test_never_dismissed_alert_reappears_using_same_row_on_relapse(self):
        sync_low_stock_alerts()
        original_id = LowStockAlert.objects.get(item=self.item).pk
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=50, location=self.wh, recorded_by=self.manager)  # recover
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.ISSUE, quantity=45, location=self.wh, recorded_by=self.manager)  # relapse (5 left, below 10)
        sync_low_stock_alerts()
        self.assertEqual(LowStockAlert.objects.filter(item=self.item).count(), 1)  # still just one row
        self.assertEqual(LowStockAlert.objects.get(item=self.item).pk, original_id)
        self.assertIn(self.item.pk, [a.item.pk for a in get_active_alerts()])

    def test_dismissed_alert_reappears_as_new_row_on_relapse(self):
        sync_low_stock_alerts()
        first_alert = LowStockAlert.objects.get(item=self.item)
        dismiss_alert(first_alert, self.manager)

        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=50, location=self.wh, recorded_by=self.manager)  # recover
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.ISSUE, quantity=45, location=self.wh, recorded_by=self.manager)  # relapse

        sync_low_stock_alerts()
        alerts = LowStockAlert.objects.filter(item=self.item).order_by("created_at")
        self.assertEqual(alerts.count(), 2)  # original (dismissed) + a fresh one
        self.assertTrue(alerts.first().dismissed)
        self.assertFalse(alerts.last().dismissed)
        self.assertIn(self.item.pk, [a.item.pk for a in get_active_alerts()])

    def test_archived_item_excluded_from_active_alerts(self):
        sync_low_stock_alerts()
        self.item.is_archived = True
        self.item.save(update_fields=["is_archived"])
        active = get_active_alerts()
        self.assertNotIn(self.item.pk, [a.item.pk for a in active])

    def test_recording_a_movement_opportunistically_creates_alert(self):
        # No explicit sync_low_stock_alerts() call — record_stock_movement's
        # own hook should create it.
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=3, location=self.wh, recorded_by=self.manager)
        self.assertTrue(LowStockAlert.objects.filter(item=self.item, dismissed=False).exists())


class AlertViewPermissionTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.staff = User.objects.create_user(username="stf", password="pass12345")
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", reorder_level=10, category=self.category, created_by=self.manager)
        self.alert = LowStockAlert.objects.create(item=self.item)

    def test_staff_cannot_view_alert_list(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("alert-list"))
        self.assertEqual(response.status_code, 403)

    def test_staff_cannot_dismiss(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.post(reverse("alert-dismiss", args=[self.alert.pk]))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_view_and_dismiss(self):
        self.client.login(username="mgr", password="pass12345")
        self.assertEqual(self.client.get(reverse("alert-list")).status_code, 200)
        response = self.client.post(reverse("alert-dismiss", args=[self.alert.pk]))
        self.assertRedirects(response, reverse("alert-list"))
        self.alert.refresh_from_db()
        self.assertTrue(self.alert.dismissed)
        self.assertEqual(self.alert.dismissed_by, self.manager)


class AlertAPITests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.staff = User.objects.create_user(username="stf", password="pass12345")
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", reorder_level=10, category=self.category, created_by=self.manager)
        self.alert = LowStockAlert.objects.create(item=self.item)

    def test_staff_cannot_list_via_api(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get("/api/alerts/")
        self.assertEqual(response.status_code, 403)

    def test_create_via_api_not_allowed(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post("/api/alerts/", {"item": self.item.pk})
        self.assertEqual(response.status_code, 405)  # ReadOnlyModelViewSet has no create

    def test_manager_can_dismiss_via_api_action(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post(f"/api/alerts/{self.alert.pk}/dismiss/")
        self.assertEqual(response.status_code, 200)
        self.alert.refresh_from_db()
        self.assertTrue(self.alert.dismissed)