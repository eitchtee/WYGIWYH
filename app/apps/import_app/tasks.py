import logging

import cachalot.api
from procrastinate.contrib.django import app

from apps.import_app.models import ImportRun
from apps.import_app.services import ImportServiceV1

logger = logging.getLogger(__name__)


@app.task(name="process_import")
def process_import(import_run_id: int, file_path: str):
    try:
        import_run = ImportRun.objects.get(id=import_run_id)
        import_service = ImportServiceV1(import_run)
        import_service.process_file(file_path)
        cachalot.api.invalidate()
    except ImportRun.DoesNotExist:
        cachalot.api.invalidate()
        raise ValueError(f"ImportRun with id {import_run_id} not found")
