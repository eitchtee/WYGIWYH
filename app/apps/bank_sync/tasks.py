from procrastinate.contrib.django import app

from apps.bank_sync.models import BankSyncService
from apps.bank_sync.sync import sync_due_services, sync_service


@app.periodic(cron="0 * * * *")
@app.task(lock="bank_sync", name="automatic_bank_sync")
def automatic_bank_sync(timestamp=None):
    sync_due_services()


@app.task(lock="bank_sync", name="manual_bank_sync")
def manual_bank_sync(service_id: int):
    service = BankSyncService.objects.filter(id=service_id).first()
    if service:
        sync_service(service)
