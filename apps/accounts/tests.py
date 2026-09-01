from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Profile


class ProfileSignalTests(TestCase):
    def test_profile_auto_created_for_regular_user(self):
        user = User.objects.create_user(username="staffuser", password="testpass123")
        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertEqual(user.profile.role, Profile.Role.STAFF)

    def test_profile_auto_created_as_manager_for_superuser(self):
        admin_user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="testpass123"
        )
        self.assertEqual(admin_user.profile.role, Profile.Role.MANAGER)


class AuthenticationViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")

    def test_login_page_loads(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_successful_login_redirects_to_home(self):
        response = self.client.post(
            reverse("login"), {"username": "testuser", "password": "testpass123"}
        )
        self.assertRedirects(response, reverse("home"))

    def test_home_requires_login(self):
        response = self.client.get(reverse("home"))
        self.assertNotEqual(response.status_code, 200)  # redirected to login

    def test_logout_requires_post(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)  # GET not allowed

    def test_logout_via_post_redirects_to_login(self):
        self.client.login(username="testuser", password="testpass123")
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))