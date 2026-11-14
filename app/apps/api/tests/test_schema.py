import tempfile

from django.core.management import call_command
from django.test import SimpleTestCase


class SchemaTests(SimpleTestCase):
    def test_schema_is_valid_without_warnings(self):
        """Keeps /api/docs/ complete: drf-spectacular warns when it can't describe something."""
        with tempfile.NamedTemporaryFile(suffix=".yml") as schema:
            call_command("spectacular", "--validate", "--fail-on-warn", "--file", schema.name)
