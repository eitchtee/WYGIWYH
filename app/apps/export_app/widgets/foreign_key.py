from import_export.widgets import ForeignKeyWidget


class AllObjectsForeignKeyWidget(ForeignKeyWidget):
    """
    ForeignKeyWidget that uses 'all_objects' manager for lookups,
    bypassing user-filtered managers like SharedObjectManager.
    Also filters by owner if available in the row data.
    """

    def get_queryset(self, value, row, *args, **kwargs):
        # Use all_objects manager if available, otherwise fall back to default
        if hasattr(self.model, "all_objects"):
            qs = self.model.all_objects.all()
            # Filter by owner if the row has an owner field and the model has owner
            if row:
                # Check for direct owner field first
                owner_id = row.get("owner") if "owner" in row else None
                # Fall back to account_owner for models like InstallmentPlan
                if not owner_id and "account_owner" in row:
                    owner_id = row.get("account_owner")
                # If still no owner, try to get it from the existing record's account
                # This handles backward compatibility with older exports
                if not owner_id and "id" in row and row.get("id"):
                    try:
                        # Try to find the existing record and get owner from its account
                        from apps.transactions.models import (
                            InstallmentPlan,
                            RecurringTransaction,
                        )

                        record_id = row.get("id")
                        # Try to find the existing InstallmentPlan or RecurringTransaction
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
                if owner_id:
                    qs = qs.filter(owner_id=owner_id)
            return qs
        return super().get_queryset(value, row, *args, **kwargs)


class AutoCreateForeignKeyWidget(ForeignKeyWidget):
    def clean(self, value, row=None, *args, **kwargs):
        if value:
            try:
                return super().clean(value, row, **kwargs)
            except self.model.DoesNotExist:
                return self.model.objects.create(name=value)
        return None


class SkipMissingForeignKeyWidget(ForeignKeyWidget):
    def clean(self, value, row=None, *args, **kwargs):
        if not value:
            return None

        try:
            return super().clean(value, row, *args, **kwargs)
        except self.model.DoesNotExist:
            return None
