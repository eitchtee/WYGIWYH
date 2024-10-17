from procrastinate import builtin_tasks
from procrastinate.contrib.django import app


@app.periodic(cron="0 4 * * *")
@app.task(queueing_lock="remove_old_jobs", pass_context=True)
async def remove_old_jobs(context, timestamp):
    return await builtin_tasks.remove_old_jobs(
        context,
        max_hours=744,
        remove_error=True,
        remove_cancelled=True,
        remove_aborted=True,
    )
