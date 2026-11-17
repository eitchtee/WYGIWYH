from django.db.models import Q
from import_export.widgets import ForeignKeyWidget


def row_owner_id(row):
    """The id of the user who owns the record being restored from ``row``."""
    if not row:
        return None
    # Check for direct owner field first
    owner_id = row.get("owner") if "owner" in row else None
    # Fall back to account_owner for models like InstallmentPlan
    if not owner_id and "account_owner" in row:
        owner_id = row.get("account_owner")
    # If still no owner, try to get it from the existing record's account
    # This handles backward compatibility with older exports
    if not owner_id and "id" in row and row.get("id"):
        try:
            from apps.transactions.models import (
                InstallmentPlan,
                RecurringTransaction,
            )

            record_id = row.get("id")
            for model_class in [InstallmentPlan, RecurringTransaction]:
                try:
                    existing = model_class.all_objects.get(id=record_id)
                    if existing.account:
                        owner_id = existing.account.owner_id
                        break
                except model_class.DoesNotExist:
                    continue
        except Exception:
            pass
    # Final fallback: use the current logged-in user
    # This handles restoring to a fresh database with older exports
    if not owner_id:
        from apps.common.middleware.thread_local import get_current_user

        user = get_current_user()
        if user and user.is_authenticated:
            owner_id = user.id
    return owner_id or None


def get_or_create_for_owner(model, name, owner_id):
    """
    The owner's own object named ``name``, else one they can see (public or
    shared with them), else a new one they own. Restore runs as the admin, so
    the user-filtered ``objects`` manager would pick the admin's objects.
    """
    named = model.all_objects.filter(name=name)
    return (
        named.filter(owner_id=owner_id).first()
        or named.filter(
            Q(visibility="public") | Q(shared_with=owner_id) | Q(owner=None)
        ).first()
        or model.all_objects.create(name=name, owner_id=owner_id)
    )


class AllObjectsForeignKeyWidget(ForeignKeyWidget):
    """
    ForeignKeyWidget that uses 'all_objects' manager for lookups,
    bypassing user-filtered managers like SharedObjectManager.
    Also filters by owner if available in the row data.
    """

    def get_queryset(self, value, row, *args, **kwargs):
        if hasattr(self.model, "all_objects"):
            qs = self.model.all_objects.all()
            if owner_id := row_owner_id(row):
                qs = qs.filter(owner_id=owner_id)
            return qs
        return super().get_queryset(value, row, *args, **kwargs)


class AutoCreateForeignKeyWidget(ForeignKeyWidget):
    def clean(self, value, row=None, *args, **kwargs):
        if value:
            return get_or_create_for_owner(self.model, value, row_owner_id(row))
        return None


class SkipMissingForeignKeyWidget(ForeignKeyWidget):
    def clean(self, value, row=None, *args, **kwargs):
        if not value:
            return None

        try:
            return super().clean(value, row, *args, **kwargs)
        except self.model.DoesNotExist:
            return None
