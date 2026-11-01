from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.dca.models import DCAStrategy
from apps.transactions.models import Transaction


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class LoadDemoDataTests(TestCase):
    def load(self, today):
        with mock.patch("django.utils.timezone.localdate", return_value=today):
            call_command("load_demo_data", verbosity=0)
        user = get_user_model().objects.get(email="demo@demo.com")
        write_current_user(user)
        self.addCleanup(delete_current_user)
        return user

    def test_dates_follow_today(self):
        """Demo data must be visible on first load, whatever day it is."""
        today = date(2031, 7, 1)  # the 1st is the edge case for "late"
        user = self.load(today)

        this_month = Transaction.objects.filter(reference_date=today.replace(day=1))
        self.assertTrue(this_month.filter(is_paid=True).exists())
        self.assertTrue(this_month.filter(description="Salary").exists())
        # Upcoming, unpaid items exist so projections have something to show
        self.assertTrue(
            Transaction.objects.filter(date__gt=today, is_paid=False).exists()
        )
        # Past unpaid items show up on the late transactions page
        self.assertTrue(
            Transaction.objects.filter(date__lt=today, is_paid=False).exists()
        )
        # Nothing in the past is left as an unpaid installment/recurring occurrence
        self.assertFalse(
            Transaction.objects.filter(
                date__lte=today, is_paid=False, installment_plan__isnull=False
            ).exists()
        )
        self.assertTrue(user.check_password("wygiwyhdemo"))

    def test_running_twice_is_a_no_op(self):
        self.load(date(2031, 7, 14))
        count = Transaction.all_objects.count()
        call_command("load_demo_data", verbosity=0)
        self.assertEqual(Transaction.all_objects.count(), count)

    def test_pages_render_with_demo_data(self):
        today = date.today()
        user = self.load(today)
        self.client.force_login(user)
        htmx = {"HTTP_HX_REQUEST": "true"}
        month = {"month": today.month, "year": today.year}
        urls = [
            reverse("monthly_overview", kwargs=month),
            reverse("monthly_summary", kwargs=month),
            reverse("monthly_account_summary", kwargs=month),
            reverse("monthly_currency_summary", kwargs=month),
            reverse("monthly_transactions_list", kwargs=month),
            reverse("net_worth_current"),
            reverse("net_worth_projected"),
            reverse("yearly_index_account"),
            reverse("transactions_all_list"),
            reverse("insights_late_transactions"),
            reverse("insights_emergency_fund"),
            reverse("quick_transactions_index"),
            reverse("rules_index"),
        ] + [
            reverse("dca_strategy_detail", kwargs={"strategy_id": s.id})
            for s in DCAStrategy.objects.all()
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url, **htmx)
                self.assertLess(response.status_code, 400)
