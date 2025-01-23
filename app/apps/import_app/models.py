import yaml

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.import_app.schemas import version_1


class ImportProfile(models.Model):
    class Versions(models.IntegerChoices):
        VERSION_1 = 1, _("Version") + " 1"

    name = models.CharField(max_length=100, verbose_name=_("Name"), unique=True)
    yaml_config = models.TextField(verbose_name=_("YAML Configuration"))
    version = models.IntegerField(
        choices=Versions,
        default=Versions.VERSION_1,
        verbose_name=_("Version"),
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]

    def clean(self):
        if self.version and self.version == self.Versions.VERSION_1:
            try:
                yaml_data = yaml.safe_load(self.yaml_config)
                version_1.ImportProfileSchema(**yaml_data)
            except Exception as e:
                raise ValidationError({"yaml_config": _("Invalid YAML Configuration")})


class ImportRun(models.Model):
    class Status(models.TextChoices):
        QUEUED = "QUEUED", _("Queued")
        PROCESSING = "PROCESSING", _("Processing")
        FAILED = "FAILED", _("Failed")
        FINISHED = "FINISHED", _("Finished")

    status = models.CharField(
        max_length=10,
        choices=Status,
        default=Status.QUEUED,
        verbose_name=_("Status"),
    )
    profile = models.ForeignKey(
        ImportProfile,
        on_delete=models.CASCADE,
    )
    file_name = models.CharField(
        max_length=10000,
        help_text=_("File name"),
    )
    transactions = models.ManyToManyField(
        "transactions.Transaction", related_name="import_runs"
    )
    tags = models.ManyToManyField(
        "transactions.TransactionTag", related_name="import_runs"
    )
    categories = models.ManyToManyField(
        "transactions.TransactionCategory", related_name="import_runs"
    )
    entities = models.ManyToManyField(
        "transactions.TransactionEntity", related_name="import_runs"
    )
    currencies = models.ManyToManyField(
        "currencies.Currency", related_name="import_runs"
    )

    logs = models.TextField(blank=True)
    processed_rows = models.IntegerField(default=0)
    total_rows = models.IntegerField(default=0)
    successful_rows = models.IntegerField(default=0)
    skipped_rows = models.IntegerField(default=0)
    failed_rows = models.IntegerField(default=0)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    @property
    def progress(self):
        if self.total_rows == 0:
            return 0
        return (self.processed_rows / self.total_rows) * 100
