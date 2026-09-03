from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile
from apps.inventory.models import Category, Item, StockMovement
from apps.inventory.services import record_stock_movement
from apps.locations.models import Location, StaffLocationAssignment


class DashboardAccessTests(TestCase):
    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)

    def test_root_url_redirects_to_dashboard(self):
        user = User.objects.create_user(username="stf", password="pass12345")
        self.client.login(username="stf", password="pass12345")
        response = self.client.get("/")
        self.assertRedirects(response, reverse("dashboard"))


class DashboardContentTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()
        self.staff = User.objects.create_user(username="stf", password="pass12345")

        self.category = Category.objects.create(name="Electronics", created_by=self.manager)
        self.low_item = Item.objects.create(
            sku="LOW-1", name="Low Widget", unit_of_measure="PCS",
            reorder_level=100, category=self.category, created_by=self.manager,
        )
        self.ok_item = Item.objects.create(
            sku="OK-1", name="Fine Widget", unit_of_measure="PCS",
            reorder_level=5, category=self.category, created_by=self.manager,
        )
        self.wh01 = Location.objects.create(name="Main Warehouse", code="WH01")
        self.store01 = Location.objects.create(name="Store One", code="STORE01")
        StaffLocationAssignment.objects.create(staff=self.staff, location=self.wh01)

        record_stock_movement(item=self.ok_item, movement_type=StockMovement.MovementType.RECEIPT, quantity=20, location=self.wh01, recorded_by=self.manager)
        record_stock_movement(item=self.low_item, movement_type=StockMovement.MovementType.RECEIPT, quantity=5, location=self.store01, recorded_by=self.manager)

    def test_manager_sees_manager_only_cards(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Archived Items")

    def test_staff_does_not_see_manager_only_cards(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("dashboard"))
        self.assertNotContains(response, "Archived Items")

    def test_low_stock_item_appears_for_both_roles(self):
        for username in ("mgr", "stf"):
            self.client.login(username=username, password="pass12345")
            response = self.client.get(reverse("dashboard"))
            self.assertContains(response, "LOW-1")
            self.client.logout()

    def test_staff_accessible_location_count_reflects_assignment(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["accessible_location_count"], 1)

    def test_manager_sees_all_active_locations_count(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["accessible_location_count"], 2)

    def test_staff_recent_activity_filtered_by_rule_7(self):
        # movement at wh01 (assigned) and store01 (not assigned) both exist from setUp
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("dashboard"))
        movements = response.context["recent_movements"]
        self.assertTrue(all(
            m.location_id == self.wh01.pk or m.source_location_id == self.wh01.pk or m.destination_location_id == self.wh01.pk
            for m in movements
        ))