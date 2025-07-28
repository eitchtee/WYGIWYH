from django.db import models
from django.conf import settings
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.common.middleware.thread_local import get_current_user


class SharedObjectManager(models.Manager):
    def get_queryset(self):
        """Return only objects the user can access"""
        user = get_current_user()
        base_qs = super().get_queryset()

        if user and user.is_authenticated:
            return base_qs.filter(
                Q(visibility="public")
                | Q(owner=user)
                | Q(shared_with=user)
                | Q(visibility="private", owner=None)
            ).distinct()

        return base_qs.filter(visibility="public")


class SharedObject(models.Model):
    # Access control enum
    class Visibility(models.TextChoices):
        private = "private", _("Private")
        is_paid = "public", _("Public")

    # Core sharing fields
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)s_owned",
        null=True,
        blank=True,
        verbose_name=_("Owner"),
    )
    visibility = models.CharField(
        max_length=10,
        choices=Visibility.choices,
        default=Visibility.private,
        verbose_name=_("Visibility"),
    )
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="%(class)s_shared",
        blank=True,
        verbose_name=_("Shared with users"),
    )

    # Use as abstract base class
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["visibility"]),
        ]

    def is_accessible_by(self, user):
        """Check if a user can access this object"""
        return (
            self.visibility == "public"
            or self.owner == user
            or (self.visibility == "shared" and user in self.shared_with.all())
        )

    def save(self, *args, **kwargs):
        if not self.pk and not self.owner:
            self.owner = get_current_user()
        super().save(*args, **kwargs)


class OwnedObjectManager(models.Manager):
    def get_queryset(self):
        """Return only objects the user can access"""
        user = get_current_user()
        base_qs = super().get_queryset()

        if user and user.is_authenticated:
            return base_qs.filter(Q(owner=user) | Q(owner=None)).distinct()

        return base_qs


class OwnedObject(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(class)s_owned",
        null=True,
        blank=True,
    )

    # Use as abstract base class
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.pk and not self.owner:
            self.owner = get_current_user()
        super().save(*args, **kwargs)
