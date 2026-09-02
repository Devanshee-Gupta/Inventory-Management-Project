from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile

from .models import Location, StaffLocationAssignment
from .services import filter_locations


class LocationModelTests(TestCase):
    def test_code_is_uppercased_on_save(self):
        loc = Location.objects.create(name="Main Warehouse", code="wh01")
        self.assertEqual(loc.code, "WH01")

    def test_code_unique(self):
        Location.objects.create(name="Main Warehouse", code="WH01")
        with self.assertRaises(Exception):
            Location.objects.create(name="Duplicate", code="WH01")

    def test_str_representation(self):
        loc = Location.objects.create(name="Store One", code="STORE01")
        self.assertEqual(str(loc), "STORE01 — Store One")

    def test_default_is_active_true(self):
        loc = Location.objects.create(name="Store Two", code="STORE02")
        self.assertTrue(loc.is_active)


class LocationTemplateViewPermissionTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()

        self.staff = User.objects.create_user(username="stf", password="pass12345")

    def test_staff_can_view_location_list(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("location-list"))
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_create_location(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("location-create"))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_location(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post(
            reverse("location-create"),
            {"name": "Main Warehouse", "code": "wh01", "description": "", "is_active": "on"},
        )
        self.assertRedirects(response, reverse("location-list"))
        self.assertTrue(Location.objects.filter(code="WH01").exists())

    def test_manager_can_deactivate_location(self):
        loc = Location.objects.create(name="Store One", code="STORE01")
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post(
            reverse("location-update", args=[loc.pk]),
            {"name": "Store One", "code": "STORE01", "description": "", "is_active": ""},
        )
        self.assertRedirects(response, reverse("location-list"))
        loc.refresh_from_db()
        self.assertFalse(loc.is_active)


class LocationAPITests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()

        self.staff = User.objects.create_user(username="stf", password="pass12345")

    def test_staff_can_list_via_api(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get("/api/locations/")
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_create_via_api(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.post("/api/locations/", {"name": "Blocked", "code": "BLK01"})
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_via_api(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post("/api/locations/", {"name": "Store Three", "code": "STORE03"})
        self.assertEqual(response.status_code, 201)

    def test_delete_not_allowed_for_anyone(self):
        loc = Location.objects.create(name="Store Four", code="STORE04")
        self.client.login(username="mgr", password="pass12345")
        response = self.client.delete(f"/api/locations/{loc.pk}/")
        self.assertEqual(response.status_code, 405)
        

class StaffLocationAssignmentModelTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="stf", password="pass12345")
        self.location = Location.objects.create(name="Main Warehouse", code="WH01")

    def test_str_representation(self):
        assignment = StaffLocationAssignment.objects.create(staff=self.staff, location=self.location)
        self.assertEqual(str(assignment), "stf → WH01")

    def test_duplicate_assignment_rejected_at_db_level(self):
        StaffLocationAssignment.objects.create(staff=self.staff, location=self.location)
        with self.assertRaises(Exception):
            StaffLocationAssignment.objects.create(staff=self.staff, location=self.location)


class AssignmentPermissionTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()

        self.staff = User.objects.create_user(username="stf", password="pass12345")
        self.location = Location.objects.create(name="Main Warehouse", code="WH01")

    def test_staff_cannot_view_assignment_list(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("assignment-list"))
        self.assertEqual(response.status_code, 403)

    def test_manager_can_create_assignment(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post(
            reverse("assignment-create"), {"staff": self.staff.pk, "location": self.location.pk}
        )
        self.assertRedirects(response, reverse("assignment-list"))
        self.assertTrue(
            StaffLocationAssignment.objects.filter(staff=self.staff, location=self.location).exists()
        )

    def test_manager_form_rejects_non_staff_user(self):
        self.client.login(username="mgr", password="pass12345")
        # manager himself is not a valid "staff" choice
        response = self.client.post(
            reverse("assignment-create"), {"staff": self.manager.pk, "location": self.location.pk}
        )
        self.assertEqual(response.status_code, 200)  # re-renders form with error
        self.assertFalse(
            StaffLocationAssignment.objects.filter(staff=self.manager, location=self.location).exists()
        )

    def test_manager_can_delete_assignment(self):
        assignment = StaffLocationAssignment.objects.create(staff=self.staff, location=self.location)
        self.client.login(username="mgr", password="pass12345")
        response = self.client.post(reverse("assignment-delete", args=[assignment.pk]))
        self.assertRedirects(response, reverse("assignment-list"))
        self.assertFalse(StaffLocationAssignment.objects.filter(pk=assignment.pk).exists())


class LocationAccessFilteringTests(TestCase):
    """Rule 7: Managers see all locations, Staff only see assigned ones."""

    def setUp(self):
        self.manager = User.objects.create_user(username="mgr", password="pass12345")
        self.manager.profile.role = Profile.Role.MANAGER
        self.manager.profile.save()

        self.staff = User.objects.create_user(username="stf", password="pass12345")

        self.wh01 = Location.objects.create(name="Main Warehouse", code="WH01")
        self.store01 = Location.objects.create(name="Store One", code="STORE01")
        StaffLocationAssignment.objects.create(staff=self.staff, location=self.wh01)

    def test_manager_sees_all_locations(self):
        self.client.login(username="mgr", password="pass12345")
        response = self.client.get(reverse("location-list"))
        self.assertContains(response, "WH01")
        self.assertContains(response, "STORE01")

    def test_staff_sees_only_assigned_location(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get(reverse("location-list"))
        self.assertContains(response, "WH01")
        self.assertNotContains(response, "STORE01")

    def test_staff_api_list_filtered_too(self):
        self.client.login(username="stf", password="pass12345")
        response = self.client.get("/api/locations/")
        codes = [loc["code"] for loc in response.json()["results"]] if "results" in response.json() else [
            loc["code"] for loc in response.json()
        ]
        self.assertIn("WH01", codes)
        self.assertNotIn("STORE01", codes)


class LocationFilterTests(TestCase):
    def setUp(self):
        self.wh01 = Location.objects.create(name="Main Warehouse", code="WH01")
        self.store01 = Location.objects.create(name="Store One", code="STORE01", is_active=False)

    def test_search_by_code(self):
        result = filter_locations(Location.objects.all(), {"q": "wh"})
        self.assertIn(self.wh01, result)
        self.assertNotIn(self.store01, result)

    def test_filter_by_active_status(self):
        result = filter_locations(Location.objects.all(), {"status": "inactive"})
        self.assertIn(self.store01, result)
        self.assertNotIn(self.wh01, result)
        