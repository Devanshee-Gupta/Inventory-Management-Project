from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Profile

from .models import Category, Item


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