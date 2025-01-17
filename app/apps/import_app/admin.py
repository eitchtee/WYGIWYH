from django.contrib import admin
from apps.import_app import models

# Register your models here.
admin.site.register(models.ImportRun)
admin.site.register(models.ImportProfile)
