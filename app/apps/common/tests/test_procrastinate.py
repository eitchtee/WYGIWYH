from unittest.mock import patch

import procrastinate
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase
from procrastinate.testing import InMemoryConnector

from apps.common.procrastinate import on_app_ready


def make_app_with_task(func):
    app = procrastinate.App(connector=InMemoryConnector())
    task = app.task(name="sample_task")(func)

    return app, task


class ProcrastinateConnectionCleanupTests(SimpleTestCase):
    def test_app_ready_closes_old_connections_around_sync_tasks(self):
        calls = []

        def sample_task(value):
            calls.append(("task", value))
            return value * 2

        app, task = make_app_with_task(sample_task)

        with patch(
            "apps.common.procrastinate.close_old_connections",
            create=True,
            side_effect=lambda: calls.append(("cleanup", None)),
        ):
            on_app_ready(app)

            result = task.func(3)

        self.assertEqual(result, 6)
        self.assertEqual(
            calls,
            [
                ("cleanup", None),
                ("task", 3),
                ("cleanup", None),
            ],
        )

    def test_app_ready_closes_old_connections_when_sync_task_raises(self):
        calls = []

        def sample_task():
            calls.append(("task", None))
            raise RuntimeError("boom")

        app, task = make_app_with_task(sample_task)

        with patch(
            "apps.common.procrastinate.close_old_connections",
            create=True,
            side_effect=lambda: calls.append(("cleanup", None)),
        ):
            on_app_ready(app)

            with self.assertRaises(RuntimeError):
                task.func()

        self.assertEqual(
            calls,
            [
                ("cleanup", None),
                ("task", None),
                ("cleanup", None),
            ],
        )


class ProcrastinateConnectionRecoveryTests(TransactionTestCase):
    def test_wrapped_task_recovers_from_closed_django_connection(self):
        def sample_task():
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone()[0]

        app, task = make_app_with_task(sample_task)
        on_app_ready(app)

        connection.ensure_connection()
        connection.connection.close()

        self.assertEqual(task.func(), 1)
