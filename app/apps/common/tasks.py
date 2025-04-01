import logging

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core import management
from django.db import DEFAULT_DB_ALIAS

from procrastinate import builtin_tasks
from procrastinate.contrib.django import app


logger = logging.getLogger(__name__)


@app.periodic(cron="0 4 * * *")
@app.task(queueing_lock="remove_old_jobs", pass_context=True, name="remove_old_jobs")
async def remove_old_jobs(context, timestamp):
    try:
        return await builtin_tasks.remove_old_jobs(
            context,
            max_hours=744,
            remove_error=True,
            remove_cancelled=True,
            remove_aborted=True,
        )
    except Exception as e:
        logger.error(
            "Error while executing 'remove_old_jobs' task",
            exc_info=True,
        )
        raise e


@app.periodic(cron="0 6 1 * *")
@app.task(queueing_lock="remove_expired_sessions", name="remove_expired_sessions")
async def remove_expired_sessions(timestamp=None):
    """Cleanup expired sessions by using Django management command."""
    try:
        await sync_to_async(management.call_command)("clearsessions", verbosity=0)
    except Exception:
        logger.error(
            "Error while executing 'remove_expired_sessions' task",
            exc_info=True,
        )


@app.periodic(cron="0 8 * * *")
@app.task(name="reset_demo_data")
def reset_demo_data(timestamp=None):
    """
    Wipes the database and loads fresh demo data if DEMO mode is active.
    Runs daily at 8:00 AM.
    """
    if not settings.DEMO:
        return  # Exit if not in demo mode

    logger.info("Demo mode active. Starting daily data reset...")

    try:
        # 1. Flush the database (wipe all data)
        logger.info("Flushing the database...")

        management.call_command(
            "flush", "--noinput", database=DEFAULT_DB_ALIAS, verbosity=1
        )
        logger.info("Database flushed successfully.")

        # 2. Load data from the fixture
        # TO-DO: Roll dates over based on today's date
        fixture_name = "fixtures/demo_data.json"
        logger.info(f"Loading data from fixture: {fixture_name}...")
        management.call_command(
            "loaddata", fixture_name, database=DEFAULT_DB_ALIAS, verbosity=1
        )
        logger.info(f"Data loaded successfully from {fixture_name}.")

        logger.info("Daily demo data reset completed.")

    except Exception as e:
        logger.exception(f"Error during daily demo data reset: {e}")
        raise
