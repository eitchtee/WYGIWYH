from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _


class Currency(models.Model):
    code = models.CharField(max_length=10, unique=True, verbose_name=_("Currency Code"))
    name = models.CharField(max_length=50, verbose_name=_("Currency Name"))
    decimal_places = models.PositiveIntegerField(
        default=2,
        validators=[MaxValueValidator(30), MinValueValidator(0)],
        verbose_name=_("Decimal Places"),
    )
    prefix = models.CharField(max_length=10, verbose_name=_("Prefix"), blank=True)
    suffix = models.CharField(max_length=10, verbose_name=_("Suffix"), blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Currency")
        verbose_name_plural = _("Currencies")
