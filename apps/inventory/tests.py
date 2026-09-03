from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile
from apps.locations.models import Location, StaffLocationAssignment
from .models import Category, Item, ItemHistory, StockMovement
from .filters import filter_categories, filter_items, filter_movements

from .services import (
    calculate_item_stock, 
    calculate_item_stock_by_location, 
    is_below_reorder, 
    record_stock_movement,
    apply_low_stock_filter,
    log_item_event,
)

import io
from django.core.files.uploadedfile import SimpleUploadedFile


class CategoryModelTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()

    def test_category_str(self):
        cat = Category.objects.create(name="Electronics", created_by=self.manager)
        self.assertEqual(str(cat), "Electronics")

    def test_category_name_unique(self):
        Category.objects.create(name="Electronics", created_by=self.manager)
        with self.assertRaises(Exception):
            Category.objects.create(name="Electronics", created_by=self.manager)


class CategoryTemplateViewPermissionTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()

        self.staff = User.objects.create_user(username="stf", password="pass12345")
        # default role is STAFF already, via the signal from STEP 2

    def test_staff_can_view_category_list(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("category-list"))
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_create_category(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("category-create"))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_category(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post(
            reverse("category-create"), {"name": "Tools", "description": "Hand tools"}
        )
        self.assertRedirects(response, reverse("category-list"))
        cat = Category.objects.get(name="Tools")
        self.assertEqual(cat.created_by, self.manager)

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("category-list"))
        self.assertEqual(response.status_code, 302)


class CategoryAPITests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()

        self.staff = User.objects.create_user(username="stf", password="pass12345")

        self.category = Category.objects.create(name="Fasteners", created_by=self.manager)

    def test_staff_can_list_via_api(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get("/api/categories/")
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_create_via_api(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.post("/api/categories/", {"name": "Blocked"})
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_via_api(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post("/api/categories/", {"name": "Adhesives"})
        self.assertEqual(response.status_code, 201)

    def test_delete_is_not_allowed_for_anyone(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.delete(f"/api/categories/{self.category.pk}/")
        self.assertEqual(response.status_code, 405)  # method not allowed
        


class ItemModelTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)

    def test_sku_uppercased_and_stripped_on_save(self):
        item = Item.objects.create(
            sku="  itm-001  ", name="Widget", unit_of_measure="PCS",
            category=self.category, created_by=self.manager,
        )
        self.assertEqual(item.sku, "ITM-001")

    def test_sku_unique(self):
        Item.objects.create(
            sku="ITM-001", name="Widget", unit_of_measure="PCS",
            category=self.category, created_by=self.manager,
        )
        with self.assertRaises(Exception):
            Item.objects.create(
                sku="ITM-001", name="Duplicate", unit_of_measure="PCS",
                category=self.category, created_by=self.manager,
            )

    def test_default_is_archived_false(self):
        item = Item.objects.create(
            sku="ITM-002", name="Gadget", unit_of_measure="PCS",
            category=self.category, created_by=self.manager,
        )
        self.assertFalse(item.is_archived)

    def test_str_representation(self):
        item = Item.objects.create(
            sku="ITM-003", name="Gizmo", unit_of_measure="PCS",
            category=self.category, created_by=self.manager,
        )
        self.assertEqual(str(item), "ITM-003 — Gizmo")


class ItemTemplateViewPermissionTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()

        self.staff = User.objects.create_user(username="stf", password="pass12345")

        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.active_item = Item.objects.create(
            sku="ITM-100", name="Active Widget", unit_of_measure="PCS",
            category=self.category, created_by=self.manager,
        )
        self.archived_item = Item.objects.create(
            sku="ITM-200", name="Archived Widget", unit_of_measure="PCS",
            category=self.category, created_by=self.manager, is_archived=True,
        )

    def test_item_list_excludes_archived_for_everyone(self):
        for username in ("mgr", "stf"):
            self.client.login(username=username, password="pass12345")
            response = self.client.get(reverse("item-list"))
            self.assertContains(response, "ITM-100")
            self.assertNotContains(response, "ITM-200")
            self.client.logout()

    def test_staff_cannot_view_archived_list(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("archived-item-list"))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_view_archived_list(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.get(reverse("archived-item-list"))
        self.assertContains(response, "ITM-200")

    def test_staff_cannot_create_item(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("item-create"))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_item(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post(reverse("item-create"), {
            "sku": "ITM-300", "name": "New Widget", "description": "",
            "unit_of_measure": "PCS", "reorder_level": 5, "category": self.category.pk,
        })
        self.assertRedirects(response, reverse("item-list"))
        item = Item.objects.get(sku="ITM-300")
        self.assertEqual(item.created_by, self.manager)

    def test_negative_reorder_level_rejected(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post(reverse("item-create"), {
            "sku": "ITM-400", "name": "Bad Widget", "description": "",
            "unit_of_measure": "PCS", "reorder_level": -5, "category": self.category.pk,
        })
        self.assertEqual(response.status_code, 200)  # re-renders with form error
        self.assertFalse(Item.objects.filter(sku="ITM-400").exists())

    def test_manager_can_archive_and_restore(self):
        self.client.login(username="mgr", password="pass12345")
        self.client.post(reverse("item-archive", args=[self.active_item.pk]))
        self.active_item.refresh_from_db()
        self.assertTrue(self.active_item.is_archived)

        self.client.post(reverse("item-restore", args=[self.active_item.pk]))
        self.active_item.refresh_from_db()
        self.assertFalse(self.active_item.is_archived)

    def test_staff_cannot_archive_item(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.post(reverse("item-archive", args=[self.active_item.pk]))
        self.assertEqual(response.status_code, 403)

    def test_archived_item_detail_still_accessible_directly(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("item-detail", args=[self.archived_item.pk]))
        self.assertEqual(response.status_code, 200)


class ItemAPITests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()

        self.staff = User.objects.create_user(username="stf", password="pass12345")

        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(
            sku="ITM-500", name="API Widget", unit_of_measure="PCS",
            category=self.category, created_by=self.manager,
        )

    def test_list_excludes_archived_by_default(self):
        Item.objects.create(
            sku="ITM-501", name="Hidden Widget", unit_of_measure="PCS",
            category=self.category, created_by=self.manager, is_archived=True,
        )
        self.client.login(username="stf", password="pass12345")
        response = self.client.get("/api/items/")
        skus = [i["sku"] for i in response.json().get("results", response.json())]
        self.assertIn("ITM-500", skus)
        self.assertNotIn("ITM-501", skus)

    def test_staff_cannot_create_via_api(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.post("/api/items/", {
            "sku": "ITM-600", "name": "Blocked", "unit_of_measure": "PCS", "category": self.category.pk,
        })
        self.assertEqual(response.status_code, 403)

    def test_manager_can_archive_via_api_action(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post(f"/api/items/{self.item.pk}/archive/")
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertTrue(self.item.is_archived)

    def test_staff_cannot_archive_via_api_action(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.post(f"/api/items/{self.item.pk}/archive/")
        self.assertEqual(response.status_code, 403)

    def test_is_archived_cannot_be_set_via_generic_update(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.patch(
            f"/api/items/{self.item.pk}/", {"is_archived": True}, content_type="application/json"
        )
        self.item.refresh_from_db()
        self.assertFalse(self.item.is_archived)  # read-only field, silently ignored

    def test_delete_not_allowed_for_anyone(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.delete(f"/api/items/{self.item.pk}/")
        self.assertEqual(response.status_code, 405)
        


class StockMovementImmutabilityTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager)
        self.wh = Location.objects.create(name="Main Warehouse", code="WH01")

    def test_movement_cannot_be_edited(self):
        movement = record_stock_movement(
            item=self.item, movement_type=StockMovement.MovementType.RECEIPT,
            quantity=10, location=self.wh, recorded_by=self.manager,
        )
        movement.quantity = 999
        with self.assertRaises(ValueError):
            movement.save()

    def test_movement_cannot_be_deleted(self):
        movement = record_stock_movement(
            item=self.item, movement_type=StockMovement.MovementType.RECEIPT,
            quantity=10, location=self.wh, recorded_by=self.manager,
        )
        with self.assertRaises(ValueError):
            movement.delete()


class StockMovementBusinessRuleTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()

        self.staff = User.objects.create_user(username="stf", password="pass12345")

        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager)
        self.archived_item = Item.objects.create(
            sku="ITM-2", name="Old Widget", unit_of_measure="PCS", category=self.category,
            created_by=self.manager, is_archived=True,
        )

        self.wh01 = Location.objects.create(name="Main Warehouse", code="WH01")
        self.store01 = Location.objects.create(name="Store One", code="STORE01")
        StaffLocationAssignment.objects.create(staff=self.staff, location=self.wh01)

    def test_receipt_increases_stock(self):
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=50, location=self.wh01, recorded_by=self.manager)
        self.assertEqual(calculate_item_stock_by_location(self.item, self.wh01), 50)

    def test_issue_rejected_when_insufficient_stock(self):
        with self.assertRaises(ValidationError):
            record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.ISSUE, quantity=5, location=self.wh01, recorded_by=self.manager)

    def test_issue_succeeds_when_sufficient_stock(self):
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=20, location=self.wh01, recorded_by=self.manager)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.ISSUE, quantity=15, location=self.wh01, recorded_by=self.manager)
        self.assertEqual(calculate_item_stock_by_location(self.item, self.wh01), 5)

    def test_transfer_rejected_when_source_insufficient(self):
        with self.assertRaises(ValidationError):
            record_stock_movement(
                item=self.item, movement_type=StockMovement.MovementType.TRANSFER, quantity=10,
                source_location=self.wh01, destination_location=self.store01, recorded_by=self.manager,
            )
        # Rule 3: transfer is atomic — a rejected transfer must create nothing at all.
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_transfer_moves_stock_between_locations(self):
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=30, location=self.wh01, recorded_by=self.manager)
        record_stock_movement(
            item=self.item, movement_type=StockMovement.MovementType.TRANSFER, quantity=10,
            source_location=self.wh01, destination_location=self.store01, recorded_by=self.manager,
        )
        self.assertEqual(calculate_item_stock_by_location(self.item, self.wh01), 20)
        self.assertEqual(calculate_item_stock_by_location(self.item, self.store01), 10)

    def test_transfer_same_source_and_destination_rejected(self):
        with self.assertRaises(ValidationError):
            record_stock_movement(
                item=self.item, movement_type=StockMovement.MovementType.TRANSFER, quantity=1,
                source_location=self.wh01, destination_location=self.wh01, recorded_by=self.manager,
            )

    def test_adjustment_blank_reason_rejected(self):
        with self.assertRaises(ValidationError):
            record_stock_movement(
                item=self.item, movement_type=StockMovement.MovementType.ADJUSTMENT, quantity=5,
                location=self.wh01, reason="", adjustment_direction=StockMovement.AdjustmentDirection.INCREASE,
                recorded_by=self.manager,
            )

    def test_adjustment_increase_always_allowed(self):
        record_stock_movement(
            item=self.item, movement_type=StockMovement.MovementType.ADJUSTMENT, quantity=100,
            location=self.wh01, reason="Found extra stock during count",
            adjustment_direction=StockMovement.AdjustmentDirection.INCREASE, recorded_by=self.manager,
        )
        self.assertEqual(calculate_item_stock_by_location(self.item, self.wh01), 100)

    def test_adjustment_decrease_rejected_when_insufficient(self):
        with self.assertRaises(ValidationError):
            record_stock_movement(
                item=self.item, movement_type=StockMovement.MovementType.ADJUSTMENT, quantity=5,
                location=self.wh01, reason="Damaged stock",
                adjustment_direction=StockMovement.AdjustmentDirection.DECREASE, recorded_by=self.manager,
            )

    def test_staff_cannot_record_adjustment(self):
        with self.assertRaises(PermissionDenied):
            record_stock_movement(
                item=self.item, movement_type=StockMovement.MovementType.ADJUSTMENT, quantity=1,
                location=self.wh01, reason="Trying anyway",
                adjustment_direction=StockMovement.AdjustmentDirection.INCREASE, recorded_by=self.staff,
            )

    def test_staff_blocked_from_unassigned_location(self):
        with self.assertRaises(PermissionDenied):
            record_stock_movement(
                item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=5,
                location=self.store01, recorded_by=self.staff,  # staff only assigned to wh01
            )

    def test_staff_allowed_at_assigned_location(self):
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=5, location=self.wh01, recorded_by=self.staff)
        self.assertEqual(calculate_item_stock_by_location(self.item, self.wh01), 5)

    def test_archived_item_blocked_from_any_movement(self):
        with self.assertRaises(ValidationError):
            record_stock_movement(item=self.archived_item, movement_type=StockMovement.MovementType.RECEIPT, quantity=5, location=self.wh01, recorded_by=self.manager)

    def test_zero_quantity_rejected(self):
        with self.assertRaises(ValidationError):
            record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=0, location=self.wh01, recorded_by=self.manager)


class MovementAPITests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.staff = User.objects.create_user(username="stf", password="pass12345")

        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager)
        self.wh01 = Location.objects.create(name="Main Warehouse", code="WH01")
        StaffLocationAssignment.objects.create(staff=self.staff, location=self.wh01)

    def test_receipt_via_api(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post("/api/movements/", {
            "item": self.item.pk, "movement_type": "RECEIPT", "quantity": 10, "location": self.wh01.pk,
        })
        self.assertEqual(response.status_code, 201)

    def test_insufficient_stock_returns_400_not_500(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post("/api/movements/", {
            "item": self.item.pk, "movement_type": "ISSUE", "quantity": 999, "location": self.wh01.pk,
        })
        self.assertEqual(response.status_code, 400)

    def test_staff_cannot_record_adjustment_via_api(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.post("/api/movements/", {
            "item": self.item.pk, "movement_type": "ADJUSTMENT", "quantity": 1,
            "location": self.wh01.pk, "reason": "test", "adjustment_direction": "INCREASE",
        })
        self.assertEqual(response.status_code, 403)

    def test_put_patch_delete_all_rejected(self):
        self.client.login(username="mgr", password="pass12345")
        create = self.client.post("/api/movements/", {
            "item": self.item.pk, "movement_type": "RECEIPT", "quantity": 10, "location": self.wh01.pk,
        })
        movement_id = create.json()["id"]
        self.assertEqual(self.client.put(f"/api/movements/{movement_id}/", {}).status_code, 405)
        self.assertEqual(self.client.patch(f"/api/movements/{movement_id}/", {}).status_code, 405)
        self.assertEqual(self.client.delete(f"/api/movements/{movement_id}/").status_code, 405)



class LedgerCalculationTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.staff = User.objects.create_user(username="stf", password="pass12345")

        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(
            sku="ITM-1", name="Widget", unit_of_measure="PCS",
            reorder_level=10, category=self.category, created_by=self.manager,
        )
        self.wh01 = Location.objects.create(name="Main Warehouse", code="WH01")
        self.store01 = Location.objects.create(name="Store One", code="STORE01")
        StaffLocationAssignment.objects.create(staff=self.staff, location=self.wh01)

    def test_total_stock_matches_sum_of_per_location_stock(self):
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=100, location=self.wh01, recorded_by=self.manager)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.TRANSFER, quantity=30, source_location=self.wh01, destination_location=self.store01, recorded_by=self.manager)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.ISSUE, quantity=20, location=self.wh01, recorded_by=self.manager)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.ADJUSTMENT, quantity=5, location=self.store01, reason="count correction", adjustment_direction=StockMovement.AdjustmentDirection.DECREASE, recorded_by=self.manager)

        direct_total = calculate_item_stock(self.item)
        summed_total = sum(
            calculate_item_stock_by_location(self.item, loc) for loc in Location.objects.all()
        )
        self.assertEqual(direct_total, summed_total)
        # 100 receipt - 20 issue - 30 transferred out + 30 transferred in - 5 decrease = 75
        self.assertEqual(direct_total, 75)

    def test_transfers_do_not_change_total_stock(self):
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=50, location=self.wh01, recorded_by=self.manager)
        before = calculate_item_stock(self.item)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.TRANSFER, quantity=20, source_location=self.wh01, destination_location=self.store01, recorded_by=self.manager)
        after = calculate_item_stock(self.item)
        self.assertEqual(before, after)

    def test_is_below_reorder_true_when_at_or_under_threshold(self):
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=10, location=self.wh01, recorded_by=self.manager)
        self.assertTrue(is_below_reorder(self.item))  # 10 stock, reorder_level 10 -> "<=" is True

    def test_is_below_reorder_false_when_above_threshold(self):
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=15, location=self.wh01, recorded_by=self.manager)
        self.assertFalse(is_below_reorder(self.item))

    def test_zero_movements_means_zero_stock_and_below_reorder(self):
        self.assertEqual(calculate_item_stock(self.item), 0)
        self.assertTrue(is_below_reorder(self.item))  # 0 <= 10


class ItemDetailStockViewTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.staff = User.objects.create_user(username="stf", password="pass12345")

        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager)
        self.wh01 = Location.objects.create(name="Main Warehouse", code="WH01")
        self.store01 = Location.objects.create(name="Store One", code="STORE01")
        StaffLocationAssignment.objects.create(staff=self.staff, location=self.wh01)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=40, location=self.wh01, recorded_by=self.manager)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=25, location=self.store01, recorded_by=self.manager)

    def test_manager_sees_full_location_breakdown(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.get(reverse("item-detail", args=[self.item.pk]))
        self.assertContains(response, "WH01")
        self.assertContains(response, "STORE01")
        self.assertContains(response, "65")  # total stock

    def test_staff_sees_only_assigned_location_in_breakdown(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("item-detail", args=[self.item.pk]))
        self.assertContains(response, "WH01")
        self.assertNotContains(response, "STORE01")


class ItemStockAPITests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.staff = User.objects.create_user(username="stf", password="pass12345")

        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", reorder_level=50, category=self.category, created_by=self.manager)
        self.wh01 = Location.objects.create(name="Main Warehouse", code="WH01")
        StaffLocationAssignment.objects.create(staff=self.staff, location=self.wh01)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=10, location=self.wh01, recorded_by=self.manager)

    def test_stock_action_returns_expected_shape(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.get(f"/api/items/{self.item.pk}/stock/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["current_stock"], 10)
        self.assertTrue(data["is_below_reorder"])  # 10 <= 50
        self.assertEqual(len(data["by_location"]), 1)

    def test_staff_can_call_stock_action_read_only(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(f"/api/items/{self.item.pk}/stock/")
        self.assertEqual(response.status_code, 200)
    


class ItemFilterTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()

        self.electronics = Category.objects.create(name="Electronics", created_by=self.manager)
        self.tools = Category.objects.create(name="Tools", created_by=self.manager)

        self.widget = Item.objects.create(sku="WID-001", name="Blue Widget", unit_of_measure="PCS", reorder_level=10, category=self.electronics, created_by=self.manager)
        self.hammer = Item.objects.create(sku="HAM-001", name="Claw Hammer", unit_of_measure="PCS", reorder_level=5, category=self.tools, created_by=self.manager)

    def test_search_matches_sku(self):
        result = filter_items(Item.objects.all(), {"q": "WID"})
        self.assertIn(self.widget, result)
        self.assertNotIn(self.hammer, result)

    def test_search_matches_name_case_insensitive(self):
        result = filter_items(Item.objects.all(), {"q": "blue"})
        self.assertIn(self.widget, result)

    def test_filter_by_category(self):
        result = filter_items(Item.objects.all(), {"category": str(self.tools.pk)})
        self.assertIn(self.hammer, result)
        self.assertNotIn(self.widget, result)

    def test_low_stock_filter_only_keeps_items_at_or_under_reorder(self):
        # widget: 0 stock, reorder_level 10 -> below.  hammer: 0 stock, reorder_level 5 -> below.
        # Give the hammer enough stock to clear its threshold.
        Location.objects.create(name="WH", code="WH01")
        from apps.locations.models import Location as LocationModel
        wh = LocationModel.objects.get(code="WH01")
        from .services import record_stock_movement
        record_stock_movement(item=self.hammer, movement_type=StockMovement.MovementType.RECEIPT, quantity=20, location=wh, recorded_by=self.manager)

        result = apply_low_stock_filter(Item.objects.all())
        self.assertIn(self.widget, result)
        self.assertNotIn(self.hammer, result)


class CategoryFilterTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        Category.objects.create(name="Electronics", created_by=self.manager)
        Category.objects.create(name="Tools", created_by=self.manager)

    def test_search_by_name(self):
        result = filter_categories(Category.objects.all(), {"q": "elect"})
        names = [c.name for c in result]
        self.assertEqual(names, ["Electronics"])


class MovementFilterTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager)
        from apps.locations.models import Location
        self.wh01 = Location.objects.create(name="Main Warehouse", code="WH01")
        self.store01 = Location.objects.create(name="Store One", code="STORE01")
        from .services import record_stock_movement
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.RECEIPT, quantity=10, location=self.wh01, recorded_by=self.manager)
        record_stock_movement(item=self.item, movement_type=StockMovement.MovementType.ISSUE, quantity=2, location=self.wh01, recorded_by=self.manager)

    def test_filter_by_movement_type(self):
        result = filter_movements(StockMovement.objects.all(), {"movement_type": "ISSUE"})
        self.assertEqual(result.count(), 1)
        self.assertEqual(result.first().movement_type, "ISSUE")

    def test_filter_by_location_matches_any_of_three_fields(self):
        result = filter_movements(StockMovement.objects.all(), {"location": str(self.wh01.pk)})
        self.assertEqual(result.count(), 2)

    def test_invalid_date_is_ignored_not_crashed(self):
        result = filter_movements(StockMovement.objects.all(), {"date_from": "not-a-date"})
        self.assertEqual(result.count(), 2)  # filter silently skipped, nothing excluded


class ItemListViewFilterTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="stf", password="pass12345")
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        Item.objects.create(sku="ABC-1", name="Alpha", unit_of_measure="PCS", category=self.category, created_by=self.manager)
        Item.objects.create(sku="XYZ-1", name="Zulu", unit_of_measure="PCS", category=self.category, created_by=self.manager)

    def test_search_query_param_filters_list(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("item-list"), {"q": "ABC"})
        self.assertContains(response, "ABC-1")
        self.assertNotContains(response, "XYZ-1")

    def test_pagination_link_preserves_filter(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("item-list"), {"q": "A"})
        self.assertIn("q=A", response.context["querystring"])
        

class ItemExportTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager)

    def test_export_returns_csv_with_header_and_row(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.get(reverse("item-export"))
        self.assertEqual(response["Content-Type"], "text/csv")
        content = response.content.decode()
        self.assertIn("sku,name", content)
        self.assertIn("ITM-1", content)

    def test_export_respects_category_filter(self):
        tools = Category.objects.create(name="Tools", created_by=self.manager)
        Item.objects.create(sku="TL-1", name="Hammer", unit_of_measure="PCS", category=tools, created_by=self.manager)
        self.client.login(username="mgr", password="pass12345")
        response = self.client.get(reverse("item-export"), {"category": str(tools.pk)})
        content = response.content.decode()
        self.assertIn("TL-1", content)
        self.assertNotIn("ITM-1", content)


class ItemImportTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.staff = User.objects.create_user(username="stf", password="pass12345")
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)

    def _csv(self, rows):
        header = "sku,name,unit_of_measure,reorder_level,category,description\n"
        body = "\n".join(rows)
        return SimpleUploadedFile("items.csv", (header + body).encode(), content_type="text/csv")

    def test_staff_cannot_import(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("item-import"))
        self.assertEqual(response.status_code, 403)

    def test_manager_import_creates_items(self):
        self.client.login(username="mgr", password="pass12345")
        upload = self._csv(["NEW-1,New Widget,PCS,5,Electronics,"])
        self.client.post(reverse("item-import"), {"csv_file": upload})
        self.assertTrue(Item.objects.filter(sku="NEW-1").exists())

    def test_duplicate_sku_is_skipped_not_overwritten(self):
        Item.objects.create(sku="DUP-1", name="Original", unit_of_measure="PCS", category=self.category, created_by=self.manager)
        self.client.login(username="mgr", password="pass12345")
        upload = self._csv(["DUP-1,Renamed,PCS,5,Electronics,"])
        self.client.post(reverse("item-import"), {"csv_file": upload})
        self.assertEqual(Item.objects.get(sku="DUP-1").name, "Original")

    def test_unknown_category_reported_as_error_not_crash(self):
        self.client.login(username="mgr", password="pass12345")
        upload = self._csv(["ERR-1,Bad Widget,PCS,5,NoSuchCategory,"])
        response = self.client.post(reverse("item-import"), {"csv_file": upload}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Item.objects.filter(sku="ERR-1").exists())


class MovementImportTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.staff = User.objects.create_user(username="stf", password="pass12345")

        from apps.locations.models import Location, StaffLocationAssignment
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager)
        self.wh01 = Location.objects.create(name="Main Warehouse", code="WH01")
        self.store01 = Location.objects.create(name="Store One", code="STORE01")
        StaffLocationAssignment.objects.create(staff=self.staff, location=self.wh01)

    def _csv(self, rows):
        header = "sku,movement_type,quantity,location,source_location,destination_location,reason,adjustment_direction\n"
        body = "\n".join(rows)
        return SimpleUploadedFile("movements.csv", (header + body).encode(), content_type="text/csv")

    def test_valid_receipt_row_creates_movement(self):
        self.client.login(username="mgr", password="pass12345")
        upload = self._csv(["ITM-1,RECEIPT,50,WH01,,,,"])
        self.client.post(reverse("movement-import"), {"csv_file": upload})
        self.assertEqual(StockMovement.objects.filter(item=self.item, movement_type="RECEIPT").count(), 1)

    def test_insufficient_stock_row_is_rejected_not_crashed(self):
        self.client.login(username="mgr", password="pass12345")
        upload = self._csv(["ITM-1,ISSUE,999,WH01,,,,"])
        response = self.client.post(reverse("movement-import"), {"csv_file": upload}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_staff_adjustment_row_rejected_receipt_row_accepted_same_file(self):
        self.client.login(username="stf", password="pass12345")
        upload = self._csv([
            "ITM-1,RECEIPT,20,WH01,,,,",
            "ITM-1,ADJUSTMENT,5,WH01,,,found extra,INCREASE",
        ])
        self.client.post(reverse("movement-import"), {"csv_file": upload})
        self.assertEqual(StockMovement.objects.filter(movement_type="RECEIPT").count(), 1)
        self.assertEqual(StockMovement.objects.filter(movement_type="ADJUSTMENT").count(), 0)

    def test_staff_row_for_unassigned_location_rejected(self):
        self.client.login(username="stf", password="pass12345")
        upload = self._csv(["ITM-1,RECEIPT,20,STORE01,,,,"])  # staff not assigned to STORE01
        self.client.post(reverse("movement-import"), {"csv_file": upload})
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_unknown_sku_reported_as_error(self):
        self.client.login(username="mgr", password="pass12345")
        upload = self._csv(["NOPE-1,RECEIPT,10,WH01,,,,"])
        response = self.client.post(reverse("movement-import"), {"csv_file": upload}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(StockMovement.objects.count(), 0)
        


class ItemHistoryImmutabilityTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager)

    def test_history_entry_cannot_be_edited(self):
        entry = log_item_event(item=self.item, event_type=ItemHistory.EventType.NOTE, performed_by=self.manager, note="test")
        entry.note = "changed"
        with self.assertRaises(ValueError):
            entry.save()

    def test_history_entry_cannot_be_deleted(self):
        entry = log_item_event(item=self.item, event_type=ItemHistory.EventType.NOTE, performed_by=self.manager, note="test")
        with self.assertRaises(ValueError):
            entry.delete()


class ItemHistoryHookTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.staff = User.objects.create_user(username="stf", password="pass12345")
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)

    def test_creating_item_via_template_logs_created_event(self):
        self.client.login(username="mgr", password="pass12345")
        self.client.post(reverse("item-create"), {
            "sku": "NEW-1", "name": "New Widget", "description": "",
            "unit_of_measure": "PCS", "reorder_level": 5, "category": self.category.pk,
        })
        item = Item.objects.get(sku="NEW-1")
        self.assertTrue(item.history.filter(event_type=ItemHistory.EventType.CREATED).exists())

    def test_updating_item_logs_correct_old_and_new_values(self):
        """Regression test for the Django ModelForm _post_clean() gotcha described above."""
        item = Item.objects.create(sku="ITM-1", name="Old Name", unit_of_measure="PCS", reorder_level=5, category=self.category, created_by=self.manager)
        self.client.login(username="mgr", password="pass12345")
        self.client.post(reverse("item-update", args=[item.pk]), {
            "sku": "ITM-1", "name": "New Name", "description": "",
            "unit_of_measure": "PCS", "reorder_level": 5, "category": self.category.pk,
        })
        entry = item.history.get(event_type=ItemHistory.EventType.UPDATED, field_name="name")
        self.assertEqual(entry.old_value, "Old Name")
        self.assertEqual(entry.new_value, "New Name")

    def test_unchanged_fields_do_not_produce_history_rows(self):
        item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", reorder_level=5, category=self.category, created_by=self.manager)
        self.client.login(username="mgr", password="pass12345")
        self.client.post(reverse("item-update", args=[item.pk]), {
            "sku": "ITM-1", "name": "Widget", "description": "",
            "unit_of_measure": "PCS", "reorder_level": 5, "category": self.category.pk,
        })
        self.assertFalse(item.history.filter(event_type=ItemHistory.EventType.UPDATED).exists())

    def test_archive_and_restore_log_events(self):
        item = Item.objects.create(sku="ITM-2", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager)
        self.client.login(username="mgr", password="pass12345")
        self.client.post(reverse("item-archive", args=[item.pk]))
        self.assertTrue(item.history.filter(event_type=ItemHistory.EventType.ARCHIVED).exists())
        self.client.post(reverse("item-restore", args=[item.pk]))
        self.assertTrue(item.history.filter(event_type=ItemHistory.EventType.RESTORED).exists())

    def test_manager_can_add_note(self):
        item = Item.objects.create(sku="ITM-3", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager)
        self.client.login(username="mgr", password="pass12345")
        self.client.post(reverse("item-add-note", args=[item.pk]), {"note": "Received a customer complaint about this batch."})
        self.assertTrue(item.history.filter(event_type=ItemHistory.EventType.NOTE).exists())

    def test_staff_cannot_add_note(self):
        item = Item.objects.create(sku="ITM-4", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager)
        self.client.login(username="stf", password="pass12345")
        response = self.client.post(reverse("item-add-note", args=[item.pk]), {"note": "trying anyway"})
        self.assertEqual(response.status_code, 403)

    def test_blank_note_rejected(self):
        item = Item.objects.create(sku="ITM-5", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager)
        self.client.login(username="mgr", password="pass12345")
        self.client.post(reverse("item-add-note", args=[item.pk]), {"note": "   "})
        self.assertFalse(item.history.filter(event_type=ItemHistory.EventType.NOTE).exists())

    def test_history_visible_for_archived_item(self):
        item = Item.objects.create(sku="ITM-6", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager, is_archived=True)
        log_item_event(item=item, event_type=ItemHistory.EventType.NOTE, performed_by=self.manager, note="Historical note")
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("item-detail", args=[item.pk]))
        self.assertContains(response, "Historical note")


class ItemHistoryAPITests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.staff = User.objects.create_user(username="stf", password="pass12345")
        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.item = Item.objects.create(sku="ITM-1", name="Widget", unit_of_measure="PCS", category=self.category, created_by=self.manager)

    def test_create_via_api_logs_created_event(self):
        self.client.login(username="mgr", password="pass12345")
        self.client.post("/api/items/", {"sku": "API-1", "name": "API Widget", "unit_of_measure": "PCS", "category": self.category.pk})
        item = Item.objects.get(sku="API-1")
        self.assertTrue(item.history.filter(event_type=ItemHistory.EventType.CREATED).exists())

    def test_update_via_api_logs_correct_diff(self):
        self.client.login(username="mgr", password="pass12345")
        self.client.patch(f"/api/items/{self.item.pk}/", {"name": "Renamed Widget"}, content_type="application/json")
        entry = self.item.history.get(event_type=ItemHistory.EventType.UPDATED, field_name="name")
        self.assertEqual(entry.old_value, "Widget")
        self.assertEqual(entry.new_value, "Renamed Widget")

    def test_history_action_returns_entries(self):
        log_item_event(item=self.item, event_type=ItemHistory.EventType.NOTE, performed_by=self.manager, note="test note")
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(f"/api/items/{self.item.pk}/history/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_staff_cannot_add_note_via_api(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.post(f"/api/items/{self.item.pk}/add_note/", {"note": "trying"})
        self.assertEqual(response.status_code, 403)