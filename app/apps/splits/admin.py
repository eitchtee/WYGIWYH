from django.contrib import admin

from apps.splits.models import (
    SplitAttachment,
    SplitEvent,
    SplitExpense,
    SplitExpenseShare,
    SplitParticipant,
    SplitPayment,
    SplitTransactionLink,
)


@admin.register(SplitEvent)
class SplitEventAdmin(admin.ModelAdmin):
    list_display = ("name", "currency", "creator", "allow_external_access", "is_archived", "created_at")
    list_filter = ("is_archived", "allow_external_access", "currency")
    search_fields = ("name", "description")


@admin.register(SplitParticipant)
class SplitParticipantAdmin(admin.ModelAdmin):
    list_display = ("name", "event", "is_external", "user", "is_active", "external_claimed_at")
    list_filter = ("is_external", "is_active")
    search_fields = ("name", "external_username", "event__name")


@admin.register(SplitExpense)
class SplitExpenseAdmin(admin.ModelAdmin):
    list_display = ("description", "event", "paid_by", "amount", "split_type", "date")
    list_filter = ("split_type", "date")
    search_fields = ("description", "notes", "event__name")


@admin.register(SplitExpenseShare)
class SplitExpenseShareAdmin(admin.ModelAdmin):
    list_display = ("expense", "participant", "amount", "percentage", "shares")


@admin.register(SplitPayment)
class SplitPaymentAdmin(admin.ModelAdmin):
    list_display = ("event", "from_participant", "to_participant", "amount", "date")
    list_filter = ("date",)


@admin.register(SplitAttachment)
class SplitAttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "event", "expense", "payment", "size", "created_at")


@admin.register(SplitTransactionLink)
class SplitTransactionLinkAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "kind", "transaction", "created_at")
    list_filter = ("kind",)
