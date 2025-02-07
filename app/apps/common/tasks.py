import logging

from asgiref.sync import sync_to_async
from django.core import management

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
