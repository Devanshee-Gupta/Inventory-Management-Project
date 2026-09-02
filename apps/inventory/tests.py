from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile
from apps.locations.models import Location, StaffLocationAssignment
from .models import Category, Item, StockMovement

from .services import (
    calculate_item_stock, 
    calculate_item_stock_by_location, 
    is_below_reorder, 
    record_stock_movement
)


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