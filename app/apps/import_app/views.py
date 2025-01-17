from django.views.generic import CreateView
from apps.import_app.models import ImportRun
from apps.import_app.services import ImportServiceV1


class ImportRunCreateView(CreateView):
    model = ImportRun
    fields = ["profile"]

    def form_valid(self, form):
        response = super().form_valid(form)

        import_run = form.instance
        file = self.request.FILES["file"]

        # Save uploaded file temporarily
        temp_file_path = f"/tmp/import_{import_run.id}.csv"
        with open(temp_file_path, "wb+") as destination:
            for chunk in file.chunks():
                destination.write(chunk)

        # Process the import
        import_service = ImportServiceV1(import_run)
        import_service.process_file(temp_file_path)

        return response
