from procrastinate.contrib.django import app

from apps.transactions.models import RecurringTransaction


@app.periodic(cron="0 0 * * *")
@app.task
def generate_recurring_transactions():
    RecurringTransaction.generate_upcoming_transactions()
