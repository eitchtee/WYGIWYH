import uuid
from decimal import Decimal
from pathlib import Path

from apps.transactions.storage import PrivateMediaStorage
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def split_attachment_path(instance, filename):
    extension = Path(filename).suffix
    return f"split_attachments/{instance.event_id}/{instance.id}{extension}"


class SplitEvent(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    currency = models.ForeignKey(
        "currencies.Currency",
        on_delete=models.PROTECT,
        related_name="split_events",
        verbose_name=_("Currency"),
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_split_events",
        verbose_name=_("Creator"),
    )
    share_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True,
        verbose_name=_("Share token"),
    )
    allow_external_access = models.BooleanField(
        default=True,
        verbose_name=_("Allow external access"),
        help_text=_(
            "Allow external participants to access this event via the shared link."
        ),
    )
    is_archived = models.BooleanField(default=False, verbose_name=_("Archived"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Split Event")
        verbose_name_plural = _("Split Events")
        db_table = "split_events"
        ordering = ["-created_at", "name"]

    def __str__(self):
        return self.name

    def can_manage(self, user) -> bool:
        return bool(user and user.is_authenticated and self.creator_id == user.id)

    def get_wygiwyh_participant(self, user):
        if not user or not user.is_authenticated:
            return None
        return self.participants.filter(user=user).first()

    def is_accessible_by_user(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        if self.creator_id == user.id:
            return True
        return self.participants.filter(user=user, is_active=True).exists()

    def regenerate_share_token(self):
        self.share_token = uuid.uuid4()
        self.save(update_fields=["share_token", "updated_at"])
        return self.share_token


class SplitParticipant(models.Model):
    event = models.ForeignKey(
        SplitEvent,
        on_delete=models.CASCADE,
        related_name="participants",
        verbose_name=_("Event"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="split_participations",
        verbose_name=_("WYGIWYH User"),
    )
    name = models.CharField(max_length=150, verbose_name=_("Name"))
    is_external = models.BooleanField(default=False, verbose_name=_("External"))
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    external_username = models.CharField(
        max_length=150,
        blank=True,
        verbose_name=_("External username"),
    )
    external_password_hash = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_("External password hash"),
    )
    external_claimed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Claimed at"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Split Participant")
        verbose_name_plural = _("Split Participants")
        db_table = "split_participants"
        ordering = ["-is_active", "name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"],
                condition=Q(user__isnull=False),
                name="unique_split_participant_user_per_event",
            ),
            models.UniqueConstraint(
                fields=["event", "name"],
                name="unique_split_participant_name_per_event",
            ),
        ]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self) -> str:
        if self.external_username:
            return f"{self.name} (@{self.external_username})"
        return self.name

    @property
    def is_claimed(self) -> bool:
        return bool(self.is_external and self.external_password_hash)

    @property
    def is_creator(self) -> bool:
        return bool(self.user_id and self.user_id == self.event.creator_id)

    def set_external_password(self, raw_password: str, username: str = ""):
        self.external_password_hash = make_password(raw_password)
        if username:
            self.external_username = username.strip()
        if not self.external_claimed_at:
            self.external_claimed_at = timezone.now()
        self.save(
            update_fields=[
                "external_password_hash",
                "external_username",
                "external_claimed_at",
            ]
        )

    def check_external_password(self, raw_password: str) -> bool:
        if not self.external_password_hash:
            return False
        return check_password(raw_password, self.external_password_hash)

    def reset_external_password(self):
        self.external_password_hash = ""
        self.external_claimed_at = None
        self.save(update_fields=["external_password_hash", "external_claimed_at"])

    def has_contributions(self) -> bool:
        return (
            self.expenses_paid.exists()
            or self.expense_shares.exists()
            or self.payments_sent.exists()
            or self.payments_received.exists()
        )

    def can_be_deleted(self) -> bool:
        return not self.is_creator and not self.has_contributions()

    def clean(self):
        super().clean()
        if self.is_external and self.user_id is not None:
            raise ValidationError(
                _("An external participant cannot be linked to a WYGIWYH user.")
            )
        if not self.is_external and self.user_id is None:
            raise ValidationError(
                _("A non-external participant must be linked to a WYGIWYH user.")
            )


class SplitExpense(models.Model):
    class SplitType(models.TextChoices):
        EQUAL = "EQUAL", _("Equal")
        EXACT = "EXACT", _("Exact amounts")
        PERCENTAGE = "PERCENTAGE", _("Percentages")
        SHARES = "SHARES", _("Shares")

    event = models.ForeignKey(
        SplitEvent,
        on_delete=models.CASCADE,
        related_name="expenses",
        verbose_name=_("Event"),
    )
    paid_by = models.ForeignKey(
        SplitParticipant,
        on_delete=models.PROTECT,
        related_name="expenses_paid",
        verbose_name=_("Paid by"),
    )
    created_by_participant = models.ForeignKey(
        SplitParticipant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses_created",
        verbose_name=_("Created by"),
    )
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
        verbose_name=_("Amount"),
    )
    date = models.DateField(default=timezone.localdate, verbose_name=_("Date"))
    split_type = models.CharField(
        max_length=16,
        choices=SplitType.choices,
        default=SplitType.EQUAL,
        verbose_name=_("Split type"),
    )
    notes = models.TextField(blank=True, verbose_name=_("Notes"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Split Expense")
        verbose_name_plural = _("Split Expenses")
        db_table = "split_expenses"
        ordering = ["-date", "-created_at", "-id"]

    def __str__(self):
        return f"{self.description} ({self.amount})"

    def clean(self):
        super().clean()
        if self.paid_by_id and self.event_id and self.paid_by.event_id != self.event_id:
            raise ValidationError(
                {"paid_by": _("Payer must be a participant of this event.")}
            )


class SplitExpenseShare(models.Model):
    expense = models.ForeignKey(
        SplitExpense,
        on_delete=models.CASCADE,
        related_name="shares",
        verbose_name=_("Expense"),
    )
    participant = models.ForeignKey(
        SplitParticipant,
        on_delete=models.PROTECT,
        related_name="expense_shares",
        verbose_name=_("Participant"),
    )
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name=_("Amount"),
    )
    percentage = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Percentage"),
    )
    shares = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Shares"),
    )

    class Meta:
        verbose_name = _("Split Expense Share")
        verbose_name_plural = _("Split Expense Shares")
        db_table = "split_expense_shares"
        ordering = ["participant__name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["expense", "participant"],
                name="unique_share_per_expense_participant",
            ),
        ]

    def __str__(self):
        return f"{self.participant.name}: {self.amount}"


class SplitPayment(models.Model):
    event = models.ForeignKey(
        SplitEvent,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name=_("Event"),
    )
    from_participant = models.ForeignKey(
        SplitParticipant,
        on_delete=models.PROTECT,
        related_name="payments_sent",
        verbose_name=_("From"),
    )
    to_participant = models.ForeignKey(
        SplitParticipant,
        on_delete=models.PROTECT,
        related_name="payments_received",
        verbose_name=_("To"),
    )
    created_by_participant = models.ForeignKey(
        SplitParticipant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments_created",
        verbose_name=_("Created by"),
    )
    amount = models.DecimalField(
        max_digits=20,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
        verbose_name=_("Amount"),
    )
    date = models.DateField(default=timezone.localdate, verbose_name=_("Date"))
    notes = models.TextField(blank=True, verbose_name=_("Notes"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Split Payment")
        verbose_name_plural = _("Split Payments")
        db_table = "split_payments"
        ordering = ["-date", "-created_at", "-id"]

    def __str__(self):
        return f"{self.from_participant.name} -> {self.to_participant.name}: {self.amount}"

    def clean(self):
        super().clean()
        errors = {}
        if (
            self.from_participant_id
            and self.to_participant_id
            and self.from_participant_id == self.to_participant_id
        ):
            errors["to_participant"] = _(
                "Sender and recipient must be different participants."
            )
        if self.event_id:
            if (
                self.from_participant_id
                and self.from_participant.event_id != self.event_id
            ):
                errors["from_participant"] = _(
                    "Sender must be a participant of this event."
                )
            if (
                self.to_participant_id
                and self.to_participant.event_id != self.event_id
            ):
                errors["to_participant"] = _(
                    "Recipient must be a participant of this event."
                )
        if errors:
            raise ValidationError(errors)


class SplitAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        SplitEvent,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name=_("Event"),
    )
    expense = models.ForeignKey(
        SplitExpense,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("Expense"),
    )
    payment = models.ForeignKey(
        SplitPayment,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("Payment"),
    )
    file = models.FileField(
        upload_to=split_attachment_path,
        storage=PrivateMediaStorage(),
        verbose_name=_("File"),
    )
    original_name = models.CharField(max_length=255, verbose_name=_("Original Name"))
    content_type = models.CharField(
        max_length=255, blank=True, verbose_name=_("Content Type")
    )
    size = models.PositiveBigIntegerField(default=0, verbose_name=_("Size"))
    uploaded_by = models.ForeignKey(
        SplitParticipant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_attachments",
        verbose_name=_("Uploaded By"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Split Attachment")
        verbose_name_plural = _("Split Attachments")
        db_table = "split_attachments"
        ordering = ["-created_at", "original_name"]

    def __str__(self):
        return self.original_name

    def clean(self):
        super().clean()
        if bool(self.expense_id) == bool(self.payment_id):
            raise ValidationError(
                _("An attachment must belong to either an expense or a payment.")
            )


class SplitTransactionLink(models.Model):
    class Kind(models.TextChoices):
        EXPENSE = "EXPENSE", _("Expense paid")
        PAYMENT_OUT = "PAYMENT_OUT", _("Payment sent")
        PAYMENT_IN = "PAYMENT_IN", _("Payment received")
        SETTLEMENT_OUT = "SETTLEMENT_OUT", _("Planned payment to send")
        SETTLEMENT_IN = "SETTLEMENT_IN", _("Planned payment to receive")

    event = models.ForeignKey(
        SplitEvent,
        on_delete=models.CASCADE,
        related_name="transaction_links",
        verbose_name=_("Event"),
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="split_transaction_links",
        verbose_name=_("User"),
    )
    transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.CASCADE,
        related_name="split_links",
        verbose_name=_("Transaction"),
    )
    kind = models.CharField(
        max_length=24,
        choices=Kind.choices,
        verbose_name=_("Kind"),
    )
    expense = models.ForeignKey(
        SplitExpense,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_links",
        verbose_name=_("Expense"),
    )
    payment = models.ForeignKey(
        SplitPayment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transaction_links",
        verbose_name=_("Payment"),
    )
    counterparty = models.ForeignKey(
        SplitParticipant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="counterparty_transaction_links",
        verbose_name=_("Counterparty"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Split Transaction Link")
        verbose_name_plural = _("Split Transaction Links")
        db_table = "split_transaction_links"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} -> Tx #{self.transaction_id}"
