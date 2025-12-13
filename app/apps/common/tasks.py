import logging
from packaging.version import parse as parse_version, InvalidVersion

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core import management
from django.db import DEFAULT_DB_ALIAS
from django.core.cache import cache

from procrastinate import builtin_tasks
from procrastinate.contrib.django import app

import requests


logger = logging.getLogger(__name__)


@app.periodic(cron="0 4 * * *")
@app.task(
    lock="remove_old_jobs",
    queueing_lock="remove_old_jobs",
    pass_context=True,
    name="remove_old_jobs",
)
async def remove_old_jobs(context, timestamp):
    try:
        return await builtin_tasks.remove_old_jobs(
            context,
            max_hours=744,
            remove_failed=True,
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
@app.task(
    lock="remove_expired_sessions",
    queueing_lock="remove_expired_sessions",
    name="remove_expired_sessions",
)
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
@app.task(lock="reset_demo_data", name="reset_demo_data")
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


@app.periodic(cron="0 */12 * * *")  # Every 12 hours
@app.task(lock="check_for_updates", name="check_for_updates")
def check_for_updates(timestamp=None):
    if not settings.CHECK_FOR_UPDATES:
        return "CHECK_FOR_UPDATES is disabled"

    url = "https://api.github.com/repos/eitchtee/WYGIWYH/releases/latest"

    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        data = response.json()
        latest_version = data.get("tag_name")

        if latest_version:
            try:
                current_v = parse_version(settings.APP_VERSION)
            except InvalidVersion:
                current_v = parse_version("0.0.0")
            try:
                latest_v = parse_version(latest_version)
            except InvalidVersion:
                latest_v = parse_version("0.0.0")

            update_info = {
                "update_available": False,
                "current_version": str(current_v),
                "latest_version": str(latest_v),
            }

            if latest_v > current_v:
                update_info["update_available"] = True

            # Cache the entire dictionary
            cache.set("update_check", update_info, 60 * 60 * 25)
            logger.info(f"Update check complete. Result: {update_info}")
        else:
            logger.warning("Could not find 'tag_name' in GitHub API response.")

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch updates from GitHub: {e}")
