from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse

class YearlyOverviewTestCase(TestCase):
    def test_example(self):
        self.assertEqual(1 + 1, 2)

    def test_yearly_overview_by_currency_view_authenticated_user(self):
        # Create a test user
        user = User.objects.create_user(username='testuser', password='testpassword')

        # Create a Client instance
        client = Client()

        # Log in the test user
        client.login(username='testuser', password='testpassword')

        # Make a GET request to the yearly_overview_currency view (e.g., for year 2023)
        # Assuming your view is named 'yearly_overview_currency' in urls.py
        # and takes year as an argument.
        # Adjust the view name and arguments if necessary.
        response = client.get(reverse('yearly_overview:yearly_overview_currency', args=[2023]))

        # Assert that the response status code is 200
        self.assertEqual(response.status_code, 200)
