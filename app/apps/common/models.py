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

    # NOTE: these two predicates must stay in sync with the ``Q`` objects built
    # by ``SharedObjectManager.get_queryset`` above. The manager filters at the
    # queryset level and these check a single instance, so they cannot share an
    # implementation; ``SharedObjectPredicateParityTests`` asserts they agree.
    def is_visible_to(self, user):
        """Whether ``user`` may read this object.

        Mirrors ``SharedObjectManager``: public objects, objects with no owner,
        the owner's own objects, and objects explicitly shared with the user.
        """
        if self.owner is None or self.visibility == "public":
            return True

        if not user or not user.is_authenticated:
            return False

        return self.owner_id == user.pk or self.shared_with.filter(pk=user.pk).exists()

    def is_editable_by(self, user):
        """Whether ``user`` may mutate this object.

        Sharing grants read access only; mutation stays with the owner. Objects
        with no owner remain editable by everyone, preserving the behaviour of
        legacy/unowned objects.
        """
        if self.owner is None:
            return True

        return bool(user and user.is_authenticated and self.owner_id == user.pk)

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
