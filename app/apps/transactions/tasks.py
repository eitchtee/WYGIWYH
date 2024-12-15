import logging

from procrastinate.contrib.django import app

from apps.transactions.models import RecurringTransaction


logger = logging.getLogger(__name__)


@app.periodic(cron="0 0 * * *")
@app.task
def generate_recurring_transactions(timestamp=None):
    try:
        RecurringTransaction.generate_upcoming_transactions()
    except Exception as e:
        logger.error(
            "Error while executing 'generate_recurring_transactions' task",
            exc_info=True,
        )
        raise e
