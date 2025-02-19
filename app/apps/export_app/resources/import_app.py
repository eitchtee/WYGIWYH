from import_export import resources

from apps.import_app.models import ImportProfile


class ImportProfileResource(resources.ModelResource):
    class Meta:
        model = ImportProfile
