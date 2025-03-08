import logging

from django.contrib.auth import get_user_model
from procrastinate.contrib.django import app

from apps.common.middleware.thread_local import write_current_user, delete_current_user
from apps.import_app.models import ImportRun
from apps.import_app.services import ImportServiceV1

logger = logging.getLogger(__name__)


@app.task(name="process_import")
def process_import(import_run_id: int, file_path: str, user_id: int):
    user = get_user_model().objects.get(id=user_id)
    write_current_user(user)

    try:
        import_run = ImportRun.objects.get(id=import_run_id)
        import_service = ImportServiceV1(import_run)
        import_service.process_file(file_path)
        delete_current_user()
    except ImportRun.DoesNotExist:
        delete_current_user()
        raise ValueError(f"ImportRun with id {import_run_id} not found")
