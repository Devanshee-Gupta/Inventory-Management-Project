from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile
from apps.alerts.models import LowStockAlert
from apps.alerts.services import dismiss_alert, get_active_alerts, sync_low_stock_alerts
from apps.inventory.models import Category, Item, ItemHistory, StockMovement
from apps.inventory.services import (
    calculate_item_stock,
    calculate_item_stock_by_location,
    is_below_reorder,
    log_item_event,
    record_stock_movement,
)
from apps.locations.models import Location, StaffLocationAssignment
from apps.locations.services import get_accessible_locations


class BaseBusinessRuleTest(TestCase):
    """Shared fixtures for every rule below: one Manager, one Staff (assigned
    to WH01 only), two locations, one category, one item."""

    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()

        self.staff = User.objects.create_user(username="stf", password="pass12345")

        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.wh01 = Location.objects.create(name="Main Warehouse", code="WH01")
        self.store01 = Location.objects.create(name="Store One", code="STORE01")
        StaffLocationAssignment.objects.create(staff=self.staff, location=self.wh01)

        self.item = Item.objects.create(
            sku="ITM-1", name="Widget", unit_of_measure="PCS",
            reorder_level=10, category=self.category, created_by=self.manager,
        )


# ============================================================
# RULE 1 — Stock quantity must never be stored directly.
# ============================================================
class Rule1_LedgerIsSourceOfTruth(BaseBusinessRuleTest):
    def test_item_model_has_no_forbidden_stock_columns(self):
        field_names = {f.name for f in Item._meta.get_fields()}
        forbidden = {"stock_quantity", "current_stock", "balance"}
        offenders = forbidden & field_names
        self.assertFalse(offenders, f"Item must never store stock directly — found: {offenders}")

    def test_full_ledger_calculation_across_all_movement_types(self):
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=100, location=self.wh01, recorded_by=self.manager)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.TRANSFER, quantity=40, source_location=self.wh01, destination_location=self.store01, recorded_by=self.manager)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.ISSUE, quantity=10, location=self.wh01, recorded_by=self.manager)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.ADJUSTMENT, quantity=5, location=self.store01, reason="count correction", adjustment_direction=StockMovement.AdjustmentDirection.DECREASE, recorded_by=self.manager)

        # 100 receipt - 40 out-transfer - 10 issue + 40 in-transfer - 5 decrease = 85
        self.assertEqual(calculate_item_stock(self.item), 85)
        self.assertEqual(calculate_item_stock_by_location(self.item, self.wh01), 50)
        self.assertEqual(calculate_item_stock_by_location(self.item, self.store01), 35)


# ============================================================
# RULE 2 — Stock movements (and history) are immutable, for everyone,
# including superusers.
# ============================================================
class Rule2_ImmutabilityEvenForSuperusers(BaseBusinessRuleTest):
    def test_superuser_cannot_edit_a_stock_movement(self):
        root = User.objects.create_superuser(username="root", email="root@example.com", password="pass12345")
        movement = record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=10, location=self.wh01, recorded_by=self.manager)
        movement.quantity = 999
        movement.recorded_by = root
        with self.assertRaises(ValueError):
            movement.save()

    def test_superuser_cannot_delete_a_stock_movement(self):
        User.objects.create_superuser(username="root2", email="root2@example.com", password="pass12345")
        movement = record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=10, location=self.wh01, recorded_by=self.manager)
        with self.assertRaises(ValueError):
            movement.delete()

    def test_item_history_is_equally_immutable(self):
        entry = log_item_event(item=self.item, event_type=ItemHistory.EventType.NOTE, performed_by=self.manager, note="original")
        entry.note = "tampered"
        with self.assertRaises(ValueError):
            entry.save()

    def test_admin_exposes_no_edit_or_delete_for_movements_or_history(self):
        from apps.inventory.admin import ItemHistoryAdmin, StockMovementAdmin
        movement_admin = StockMovementAdmin(StockMovement, None)
        history_admin = ItemHistoryAdmin(ItemHistory, None)
        for admin_instance in (movement_admin, history_admin):
            self.assertFalse(admin_instance.has_add_permission(None))
            self.assertFalse(admin_instance.has_change_permission(None))
            self.assertFalse(admin_instance.has_delete_permission(None))


# ============================================================
# RULE 3 — Transfers are atomic; negative stock is never allowed.
# ============================================================
class Rule3_AtomicTransfersNoNegativeStock(BaseBusinessRuleTest):
    def test_issue_beyond_available_stock_rejected_and_leaves_zero_stock(self):
        with self.assertRaises(ValidationError):
            record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.ISSUE, quantity=1, location=self.wh01, recorded_by=self.manager)
        self.assertEqual(calculate_item_stock(self.item), 0)

    def test_rejected_transfer_creates_no_row_and_leaves_source_untouched(self):
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=10, location=self.wh01, recorded_by=self.manager)
        with self.assertRaises(ValidationError):
            record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.TRANSFER, quantity=999, source_location=self.wh01, destination_location=self.store01, recorded_by=self.manager)
        self.assertEqual(StockMovement.objects.filter(movement_type=StockMovement.MovementType.TRANSFER).count(), 0)
        self.assertEqual(calculate_item_stock_by_location(self.item, self.wh01), 10)

    def test_exact_balance_transfer_succeeds_then_further_transfer_from_empty_source_fails(self):
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=50, location=self.wh01, recorded_by=self.manager)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.TRANSFER, quantity=50, source_location=self.wh01, destination_location=self.store01, recorded_by=self.manager)
        self.assertEqual(calculate_item_stock_by_location(self.item, self.wh01), 0)
        with self.assertRaises(ValidationError):
            record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.TRANSFER, quantity=1, source_location=self.wh01, destination_location=self.store01, recorded_by=self.manager)


# ============================================================
# RULE 4 — Adjustments require a reason; blank is rejected.
# ============================================================
class Rule4_AdjustmentsRequireReason(BaseBusinessRuleTest):
    def test_blank_reason_rejected_at_service_layer(self):
        with self.assertRaises(ValidationError):
            record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.ADJUSTMENT, quantity=5, location=self.wh01, reason="", adjustment_direction=StockMovement.AdjustmentDirection.INCREASE, recorded_by=self.manager)

    def test_whitespace_only_reason_rejected(self):
        with self.assertRaises(ValidationError):
            record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.ADJUSTMENT, quantity=5, location=self.wh01, reason="   ", adjustment_direction=StockMovement.AdjustmentDirection.INCREASE, recorded_by=self.manager)

    def test_blank_reason_rejected_via_api_with_400_not_500(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post("/api/movements/", {
            "item": self.item.pk, "movement_type": "ADJUSTMENT", "quantity": 5,
            "location": self.wh01.pk, "reason": "", "adjustment_direction": "INCREASE",
        })
        self.assertEqual(response.status_code, 400)


# ============================================================
# RULE 5 — Archived items: hidden from normal screens, cannot receive
# new movements, but their history stays visible.
# ============================================================
class Rule5_ArchivedItemLifecycle(BaseBusinessRuleTest):
    def test_full_archive_lifecycle_across_list_detail_and_movement_history(self):
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=20, location=self.wh01, recorded_by=self.manager)
        self.item.is_archived = True
        self.item.save(update_fields=["is_archived", "updated_at"])

        self.client.login(username="mgr", password="pass12345")

        list_response = self.client.get(reverse("item-list"))
        self.assertNotContains(list_response, self.item.sku)

        detail_response = self.client.get(reverse("item-detail", args=[self.item.pk]))
        self.assertEqual(detail_response.status_code, 200)

        movement_history_response = self.client.get(reverse("movement-list"))
        self.assertContains(movement_history_response, self.item.sku)

    def test_archived_item_cannot_receive_any_movement_type(self):
        self.item.is_archived = True
        self.item.save(update_fields=["is_archived", "updated_at"])
        with self.assertRaises(ValidationError):
            record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=5, location=self.wh01, recorded_by=self.manager)


# ============================================================
# RULE 6 — Server-side authorization only; client-supplied privilege
# data is never trusted.
# ============================================================
class Rule6_ServerSideAuthorizationOnly(BaseBusinessRuleTest):
    def test_client_cannot_spoof_who_recorded_a_movement(self):
        impersonated = User.objects.create_user(username="mgr2", password="pass12345")
        impersonated.profile.role = Profile.Role.MANAGER
        impersonated.profile.save()

        self.client.login(username="mgr", password="pass12345")
        response = self.client.post("/api/movements/", {
            "item": self.item.pk, "movement_type": "RECEIPT", "quantity": 5,
            "location": self.wh01.pk, "recorded_by": impersonated.pk,
        })
        self.assertEqual(response.status_code, 201)
        movement = StockMovement.objects.latest("created_at")
        self.assertEqual(movement.recorded_by, self.manager)  # the real session user, not the payload

    def test_is_archived_cannot_be_set_by_a_generic_client_patch(self):
        self.client.login(username="mgr", password="pass12345")
        self.client.patch(f"/api/items/{self.item.pk}/", {"is_archived": True}, content_type="application/json")
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_archived)

    def test_staff_blocked_from_manager_only_action_server_side(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.post(reverse("movement-adjustment"), {
            "item": self.item.pk, "quantity": 5, "location": self.wh01.pk,
            "reason": "trying anyway", "adjustment_direction": "INCREASE",
        })
        self.assertEqual(response.status_code, 403)


# ============================================================
# RULE 7 — Managers see everything; Staff are confined to their
# assigned locations, everywhere that matters.
# ============================================================
class Rule7_LocationAccessControlEndToEnd(BaseBusinessRuleTest):
    def test_staff_workflow_stays_confined_across_locations_movements_and_dashboard(self):
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=30, location=self.wh01, recorded_by=self.manager)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=15, location=self.store01, recorded_by=self.manager)

        self.client.login(username="stf", password="pass12345")

        locations_response = self.client.get(reverse("location-list"))
        self.assertContains(locations_response, "WH01")
        self.assertNotContains(locations_response, "STORE01")

        dashboard_response = self.client.get(reverse("dashboard"))
        self.assertEqual(dashboard_response.context["accessible_location_count"], 1)

        movements_response = self.client.get(reverse("movement-list"))
        movements = movements_response.context["movements"]
        self.assertTrue(all(m.location_id == self.wh01.pk for m in movements))

    def test_staff_cannot_record_movement_at_an_unassigned_location(self):
        with self.assertRaises(PermissionDenied):
            record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=5, location=self.store01, recorded_by=self.staff)

    def test_manager_is_exempt_from_all_location_restrictions(self):
        self.assertEqual(get_accessible_locations(self.manager).count(), Location.objects.count())


# ============================================================
# Cross-rule integration — the low-stock alert lifecycle touches
# Rules 1 (live computation) and 7 (visibility) at once.
# ============================================================
class CrossRule_LowStockAlertLifecycle(BaseBusinessRuleTest):
    def test_alert_lifecycle_end_to_end(self):
        # Item starts at 0 stock, reorder_level 10 -> immediately below.
        sync_low_stock_alerts()
        self.assertTrue(is_below_reorder(self.item))
        active = get_active_alerts()
        self.assertIn(self.item.pk, [a.item.pk for a in active])

        alert = LowStockAlert.objects.get(item=self.item, dismissed=False)
        dismiss_alert(alert, self.manager)

        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=50, location=self.wh01, recorded_by=self.manager)
        self.assertFalse(is_below_reorder(self.item))

        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.ISSUE, quantity=45, location=self.wh01, recorded_by=self.manager)
        sync_low_stock_alerts()
        self.assertEqual(LowStockAlert.objects.filter(item=self.item).count(), 2)  # dismissed original + fresh reappearance
        self.assertIn(self.item.pk, [a.item.pk for a in get_active_alerts()])