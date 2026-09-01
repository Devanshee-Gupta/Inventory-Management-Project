from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile

from .models import Category


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