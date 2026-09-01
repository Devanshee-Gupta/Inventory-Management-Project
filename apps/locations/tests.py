from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile

from .models import Location


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