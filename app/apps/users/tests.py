from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

class UsersTestCase(TestCase):
    def test_example(self):
        self.assertEqual(1 + 1, 2)

    def test_users_index_view_superuser(self):
        # Create a superuser
        superuser = User.objects.create_user(
            username='superuser',
            password='superpassword',
            is_staff=True,
            is_superuser=True
        )

        # Create a Client instance
        client = Client()

        # Log in the superuser
        client.login(username='superuser', password='superpassword')

        # Make a GET request to the users_index view
        # Assuming your users_index view is named 'users_index' in the 'users' app namespace
        response = client.get(reverse('users:users_index'))

        # Assert that the response status code is 200
        self.assertEqual(response.status_code, 200)
