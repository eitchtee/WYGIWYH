from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class UserAuthTests(TestCase):
    def setUp(self):
        self.user_credentials = {
            "email": "testuser@example.com",
            "password": "testpassword123",
        }
        self.user = User.objects.create_user(**self.user_credentials)

    def test_user_creation(self):
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(self.user.email, self.user_credentials["email"])
        self.assertTrue(self.user.check_password(self.user_credentials["password"]))

    def test_user_login(self):
        # Check that the user can log in with correct credentials
        login_url = reverse("login")
        response = self.client.post(login_url, self.user_credentials)
        self.assertEqual(response.status_code, 302)  # Redirects on successful login
        # Assuming 'index' is the name of the view users are redirected to after login.
        # You might need to change "index" to whatever your project uses.
        self.assertRedirects(response, reverse("index"))
        self.assertTrue("_auth_user_id" in self.client.session)

    def test_user_login_invalid_credentials(self):
        # Check that login fails with incorrect credentials
        login_url = reverse("login")
        invalid_credentials = {
            "email": self.user_credentials["email"],
            "password": "wrongpassword",
        }
        response = self.client.post(login_url, invalid_credentials)
        self.assertEqual(response.status_code, 200)  # Stays on the login page
        self.assertFormError(response, "form", None, _("Invalid e-mail or password"))
        self.assertFalse("_auth_user_id" in self.client.session)


    def test_user_logout(self):
        # Log in the user first
        self.client.login(**self.user_credentials)
        self.assertTrue("_auth_user_id" in self.client.session)

        # Test logout
        logout_url = reverse("logout")
        response = self.client.get(logout_url)
        self.assertEqual(response.status_code, 302)  # Redirects on successful logout
        self.assertRedirects(response, reverse("login"))
        self.assertFalse("_auth_user_id" in self.client.session)


class UserProfileUpdateTests(TestCase):
    def setUp(self):
        self.user_credentials = {
            "email": "testuser@example.com",
            "password": "testpassword123",
            "first_name": "Test",
            "last_name": "User",
        }
        self.user = User.objects.create_user(**self.user_credentials)

        self.superuser_credentials = {
            "email": "superuser@example.com",
            "password": "superpassword123",
        }
        self.superuser = User.objects.create_superuser(**self.superuser_credentials)

        self.edit_url = reverse("user_edit", kwargs={"pk": self.user.pk})
        self.update_data = {
            "first_name": "Updated First Name",
            "last_name": "Updated Last Name",
            "email": "updateduser@example.com",
        }

    def test_user_can_update_own_profile(self):
        self.client.login(email=self.user_credentials["email"], password=self.user_credentials["password"])
        response = self.client.post(self.edit_url, self.update_data)
        self.assertEqual(response.status_code, 204) # Successful update returns HX-Trigger with 204
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, self.update_data["first_name"])
        self.assertEqual(self.user.last_name, self.update_data["last_name"])
        self.assertEqual(self.user.email, self.update_data["email"])

    def test_user_cannot_update_other_user_profile(self):
        # Create another regular user
        other_user_credentials = {
            "email": "otheruser@example.com",
            "password": "otherpassword123",
        }
        other_user = User.objects.create_user(**other_user_credentials)
        other_user_edit_url = reverse("user_edit", kwargs={"pk": other_user.pk})

        # Log in as the first user
        self.client.login(email=self.user_credentials["email"], password=self.user_credentials["password"])

        # Attempt to update other_user's profile
        response = self.client.post(other_user_edit_url, self.update_data)
        self.assertEqual(response.status_code, 403)  # PermissionDenied

        other_user.refresh_from_db()
        self.assertNotEqual(other_user.first_name, self.update_data["first_name"])

    def test_superuser_can_update_other_user_profile(self):
        self.client.login(email=self.superuser_credentials["email"], password=self.superuser_credentials["password"])
        response = self.client.post(self.edit_url, self.update_data)
        self.assertEqual(response.status_code, 204) # Successful update returns HX-Trigger with 204

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, self.update_data["first_name"])
        self.assertEqual(self.user.last_name, self.update_data["last_name"])
        self.assertEqual(self.user.email, self.update_data["email"])

    def test_profile_update_password_change(self):
        self.client.login(email=self.user_credentials["email"], password=self.user_credentials["password"])
        password_data = {
            "new_password1": "newsecurepassword",
            "new_password2": "newsecurepassword",
        }
        # Include existing data to pass form validation for other fields if they are required
        full_update_data = {**self.update_data, **password_data}
        response = self.client.post(self.edit_url, full_update_data)
        self.assertEqual(response.status_code, 204)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(password_data["new_password1"]))
        # Ensure other details were also updated
        self.assertEqual(self.user.first_name, self.update_data["first_name"])

    def test_profile_update_password_mismatch(self):
        self.client.login(email=self.user_credentials["email"], password=self.user_credentials["password"])
        password_data = {
            "new_password1": "newsecurepassword",
            "new_password2": "mismatchedpassword", # Passwords don't match
        }
        full_update_data = {**self.update_data, **password_data}
        response = self.client.post(self.edit_url, full_update_data)
        self.assertEqual(response.status_code, 200) # Should return the form with errors
        self.assertContains(response, "The two password fields didn&#39;t match.") # Check for error message

        self.user.refresh_from_db()
        # Ensure password was NOT changed
        self.assertTrue(self.user.check_password(self.user_credentials["password"]))
        # Ensure other details were also NOT updated due to form error
        self.assertNotEqual(self.user.first_name, self.update_data["first_name"])
