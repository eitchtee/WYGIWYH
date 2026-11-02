from unittest import mock

from django.core.cache import caches
from django.test import SimpleTestCase, override_settings

from apps.common.tasks import check_for_updates
from apps.common.templatetags.cache_access import get_update_check

# Distinct LOCATIONs: LocMemCache aliases with the same LOCATION share one store and would hide wrong-cache bugs
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "default"},
    "update_check": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "update_check"},
}


@override_settings(CACHES=CACHES)
class GetUpdateCheckTests(SimpleTestCase):
    def setUp(self):
        caches["update_check"].clear()

    def render_with(self, app_version, latest):
        if latest:
            caches["update_check"].set("latest_version", latest)
        with self.settings(APP_VERSION=app_version):
            return get_update_check()

    def test_newer_release_is_available(self):
        self.assertEqual(
            self.render_with("1.0.0", "1.1.0"),
            {"update_available": True, "latest_version": "1.1.0"},
        )

    def test_after_upgrade_no_update(self):
        self.assertFalse(self.render_with("1.1.0", "1.1.0")["update_available"])
        self.assertFalse(self.render_with("1.2.0", "1.1.0")["update_available"])

    def test_nothing_cached(self):
        self.assertEqual(
            self.render_with("1.0.0", None),
            {"update_available": False, "latest_version": "N/A"},
        )

    def test_unknown_app_version_hides_update(self):
        self.assertFalse(self.render_with("unknown", "1.1.0")["update_available"])

    @override_settings(CHECK_FOR_UPDATES=False)
    def test_disabled_hides_cached_update(self):
        self.assertFalse(self.render_with("1.0.0", "1.1.0")["update_available"])


@override_settings(CACHES=CACHES, CHECK_FOR_UPDATES=True)
class CheckForUpdatesTaskTests(SimpleTestCase):
    def setUp(self):
        caches["update_check"].clear()

    def run_task(self, tag):
        with mock.patch("apps.common.tasks.requests.get") as get:
            get.return_value.json.return_value = {"tag_name": tag}
            check_for_updates.func()
        return caches["update_check"].get("latest_version")

    def test_stores_normalized_version(self):
        self.assertEqual(self.run_task("v1.8.0"), "1.8.0")

    def test_invalid_tag_keeps_previous_value(self):
        caches["update_check"].set("latest_version", "1.7.0")
        self.assertEqual(self.run_task("not-a-version"), "1.7.0")
