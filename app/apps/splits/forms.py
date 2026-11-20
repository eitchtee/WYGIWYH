from decimal import Decimal, InvalidOperation

from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Layout, Row
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Account
from apps.common.widgets.crispy.daisyui import Switch
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.datepicker import AirDatePickerInput
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput
from apps.common.fields.forms.dynamic_select import (
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)
from apps.common.widgets.tom_select import TomSelect, TransactionSelect
from apps.currencies.models import Currency
from apps.splits.models import (
    SplitAttachment,
    SplitEvent,
    SplitExpense,
    SplitParticipant,
    SplitPayment,
    SplitTransactionLink,
)
from apps.splits.services.splitting import compute_expense_shares
from apps.transactions.forms import MultipleFileField
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionEntity,
    TransactionTag,
)

User = get_user_model()


def _participant_label(p: SplitParticipant) -> str:
    return p.name if p.is_active else _("%(name)s (inactive)") % {"name": p.name}


class SplitEventForm(forms.ModelForm):
    class Meta:
        model = SplitEvent
        fields = [
            "name",
            "currency",
            "description",
            "allow_external_access",
            "is_archived",
        ]
        widgets = {
            "currency": TomSelect(clear_button=False),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["currency"].queryset = Currency.objects.filter(
            is_archived=False
        ).order_by("name")
        if self.instance and self.instance.pk:
            # Allow keeping current currency even if archived
            self.fields["currency"].queryset = Currency.objects.filter(
                is_archived=False
            ) | Currency.objects.filter(pk=self.instance.currency_id)
            # Stored amounts are not converted, so changing currency would corrupt them
            if self.instance.expenses.exists() or self.instance.payments.exists():
                self.fields["currency"].disabled = True
                self.fields["currency"].help_text = _(
                    "The currency can't be changed after expenses or payments are added."
                )

        self.helper = FormHelper()
        self.helper.form_tag = False
        fields_layout = [
            "name",
            "currency",
            "description",
            Switch("allow_external_access"),
        ]
        if self.instance and self.instance.pk:
            fields_layout.append(Switch("is_archived"))
            fields_layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Update"), css_class="btn btn-primary")
                )
            )
        else:
            self.fields.pop("is_archived", None)
            fields_layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Add"), css_class="btn btn-primary")
                )
            )
        self.helper.layout = Layout(*fields_layout)


class AddWygiwyhParticipantForm(forms.Form):
    user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        label=_("WYGIWYH User"),
        widget=TomSelect(clear_button=False),
    )

    def __init__(self, *args, event: SplitEvent, **kwargs):
        super().__init__(*args, **kwargs)
        existing_user_ids = event.participants.filter(
            user__isnull=False
        ).values_list("user_id", flat=True)
        self.fields["user"].queryset = (
            User.objects.filter(is_active=True)
            .exclude(id__in=existing_user_ids)
            .order_by("first_name", "last_name", "email")
        )
        self.fields["user"].label_from_instance = self._user_label

    @staticmethod
    def _user_label(u):
        full = f"{u.first_name} {u.last_name}".strip()
        return f"{full} ({u.email})" if full else u.email


class AddExternalParticipantForm(forms.Form):
    name = forms.CharField(
        max_length=150,
        label=_("Name"),
        widget=forms.TextInput(attrs={"placeholder": _("e.g. Alex")}),
    )

    def __init__(self, *args, event: SplitEvent, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise ValidationError(_("Name cannot be empty."))
        if self.event.participants.filter(name__iexact=name).exists():
            raise ValidationError(
                _("A participant named '%(name)s' already exists in this event.")
                % {"name": name}
            )
        return name


class SplitExpenseForm(forms.ModelForm):
    attachments = MultipleFileField(
        required=False,
        label=_("Attachments"),
        help_text=_("Optional receipts or files."),
    )

    class Meta:
        model = SplitExpense
        fields = ["description", "amount", "date", "paid_by", "split_type", "notes"]
        widgets = {
            "date": AirDatePickerInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, event: SplitEvent, default_payer: SplitParticipant | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event

        # Include active participants, plus any inactive participant already referenced on this expense
        active_qs = event.participants.filter(is_active=True)
        if self.instance and self.instance.pk:
            referenced_ids = list(
                self.instance.shares.values_list("participant_id", flat=True)
            ) + [self.instance.paid_by_id]
            self.available_participants = list(
                event.participants.filter(
                    id__in=referenced_ids
                ).union(active_qs).order_by("-is_active", "name", "id")
            )
            payer_qs = event.participants.filter(
                id__in=[p.id for p in self.available_participants]
            ).order_by("-is_active", "name", "id")
        else:
            self.available_participants = list(active_qs.order_by("name", "id"))
            payer_qs = active_qs.order_by("name", "id")

        self.fields["paid_by"].queryset = payer_qs
        self.fields["paid_by"].label_from_instance = _participant_label
        self.fields["paid_by"].empty_label = None
        self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput(
            decimal_places=event.currency.decimal_places,
            attrs={"inputmode": "decimal"},
        )
        self.fields["amount"].label = _("Amount (%(code)s)") % {"code": event.currency.code}
        if not self.instance.pk:
            self.fields["date"].initial = timezone.localdate()
            if default_payer and payer_qs.filter(pk=default_payer.pk).exists():
                self.fields["paid_by"].initial = default_payer

        self.computed_shares = []

    def clean(self):
        cleaned = super().clean()
        amount = cleaned.get("amount")
        split_type = cleaned.get("split_type")
        if amount is None or not split_type:
            return cleaned

        # Parse selected participants and per-participant split values from POST data
        selected_ids = self.data.getlist("share_participants")
        selected_id_set = set()
        for raw_id in selected_ids:
            try:
                selected_id_set.add(int(raw_id))
            except (TypeError, ValueError):
                pass

        participants_by_id = {p.id: p for p in self.available_participants}
        selected_participants = [
            participants_by_id[pid]
            for pid in participants_by_id
            if pid in selected_id_set
        ]

        values_by_id: dict[int, Decimal] = {}
        if split_type != SplitExpense.SplitType.EQUAL:
            for p in selected_participants:
                raw_val = (self.data.get(f"share_value_{p.id}") or "").strip()
                if raw_val == "":
                    values_by_id[p.id] = Decimal("0")
                else:
                    try:
                        # <input type=number> always posts "12.5", never the locale format
                        values_by_id[p.id] = Decimal(raw_val)
                    except InvalidOperation:
                        raise ValidationError(
                            _("Invalid split value for %(name)s.") % {"name": p.name}
                        )

        self.computed_shares = compute_expense_shares(
            total_amount=amount,
            split_type=split_type,
            participants=selected_participants,
            decimal_places=self.event.currency.decimal_places,
            values_by_participant_id=values_by_id,
        )
        return cleaned


class SplitPaymentForm(forms.ModelForm):
    attachments = MultipleFileField(
        required=False,
        label=_("Attachments"),
        help_text=_("Optional proof of payment."),
    )

    class Meta:
        model = SplitPayment
        fields = ["from_participant", "to_participant", "amount", "date", "notes"]
        widgets = {
            "date": AirDatePickerInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, event: SplitEvent, actor=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        self.actor = actor
        qs = event.participants.filter(is_active=True).order_by("name", "id")
        if self.instance and self.instance.pk:
            qs = event.participants.filter(
                id__in=list(qs.values_list("id", flat=True))
                + [self.instance.from_participant_id, self.instance.to_participant_id]
            ).order_by("-is_active", "name", "id")
        for name in ("from_participant", "to_participant"):
            self.fields[name].queryset = qs
            self.fields[name].label_from_instance = _participant_label
        self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput(
            decimal_places=event.currency.decimal_places,
            attrs={"inputmode": "decimal"},
        )
        self.fields["amount"].label = _("Amount (%(code)s)") % {"code": event.currency.code}
        if not self.instance.pk:
            self.fields["date"].initial = timezone.localdate()

    def clean(self):
        cleaned = super().clean()
        from_p = cleaned.get("from_participant")
        to_p = cleaned.get("to_participant")
        if from_p and to_p and from_p == to_p:
            self.add_error(
                "to_participant",
                _("Sender and recipient must be different participants."),
            )
        if (
            self.actor
            and from_p
            and to_p
            and not self.actor.can_record_payment(from_p.id, to_p.id)
        ):
            raise ValidationError(
                _("You can only record payments you sent or received.")
            )
        return cleaned


class SplitAttachmentUploadForm(forms.Form):
    attachments = MultipleFileField(
        required=True,
        label=_("Attachments"),
    )

    def save(self, *, event: SplitEvent, uploaded_by: SplitParticipant | None, expense=None, payment=None):
        created = []
        for f in self.cleaned_data.get("attachments") or []:
            created.append(
                SplitAttachment.objects.create(
                    event=event,
                    expense=expense,
                    payment=payment,
                    file=f,
                    original_name=f.name,
                    content_type=getattr(f, "content_type", ""),
                    size=f.size,
                    uploaded_by=uploaded_by,
                )
            )
        return created


class SplitTransactionSyncForm(forms.Form):
    class Mode(models.TextChoices):
        CREATE = "create", _("Create new WYGIWYH transaction")
        LINK = "link", _("Link existing WYGIWYH transaction")

    mode = forms.ChoiceField(
        choices=Mode.choices,
        initial=Mode.CREATE,
        widget=forms.RadioSelect,
        label=_("Action"),
    )
    # Create mode fields
    account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        required=False,
        label=_("Account"),
        widget=TomSelect(clear_button=False, group_by="group"),
    )
    category = DynamicModelChoiceField(
        create_field="name",
        model=TransactionCategory,
        required=False,
        label=_("Category"),
        queryset=TransactionCategory.objects.none(),
    )
    tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
        queryset=TransactionTag.objects.none(),
    )
    entities = DynamicModelMultipleChoiceField(
        model=TransactionEntity,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Entities"),
        queryset=TransactionEntity.objects.none(),
    )
    amount = forms.DecimalField(
        max_digits=20,
        decimal_places=6,
        required=False,
        label=_("Amount"),
    )
    date = forms.DateField(
        required=False,
        label=_("Date"),
        widget=AirDatePickerInput(),
    )
    description = forms.CharField(
        max_length=500,
        required=False,
        label=_("Description"),
    )
    is_paid = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Mark as paid"),
    )
    notes = forms.CharField(
        required=False,
        label=_("Notes"),
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    # Link mode field
    existing_transaction = DynamicModelChoiceField(
        model=Transaction,
        to_field_name="id",
        required=False,
        label=_("Transaction"),
        queryset=Transaction.objects.none(),
        widget=TransactionSelect(clear_button=True),
        help_text=_("Type to search for a transaction to link"),
    )

    def __init__(self, *args, user, event: SplitEvent, tx_type: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.event = event
        self.tx_type = tx_type

        accounts = Account.objects.filter(is_archived=False).order_by("name")
        self.fields["account"].queryset = accounts
        # Amounts are in the event currency, so only preselect a same-currency account
        same_currency = accounts.filter(currency=event.currency)
        default_acc = getattr(getattr(user, "settings", None), "default_account", None)
        if default_acc and same_currency.filter(pk=default_acc.pk).exists():
            self.fields["account"].initial = default_acc
        else:
            self.fields["account"].initial = same_currency.first()

        self.fields["category"].queryset = TransactionCategory.objects.filter(active=True)
        self.fields["tags"].queryset = TransactionTag.objects.filter(active=True)
        self.fields["entities"].queryset = TransactionEntity.objects.filter(active=True)
        self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput(
            decimal_places=event.currency.decimal_places,
            attrs={"inputmode": "decimal"},
        )

        # Search only transactions of the matching type in the event currency
        picker = self.fields["existing_transaction"]
        picker.widget.load_income = tx_type == Transaction.Type.INCOME
        picker.widget.load_expense = tx_type == Transaction.Type.EXPENSE
        picker.widget.filters = {"currency": event.currency_id}
        selected = self.data.get("existing_transaction") if self.is_bound else None
        # Only the selected one: the picker loads the rest by search
        picker.queryset = Transaction.objects.filter(
            id=selected if str(selected or "").isdigit() else None
        )

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("mode")
        if mode == self.Mode.CREATE:
            if not cleaned.get("account"):
                self.add_error("account", _("Please select an account."))
            if not cleaned.get("amount") or cleaned["amount"] <= 0:
                self.add_error("amount", _("Amount must be greater than zero."))
            if not cleaned.get("date"):
                cleaned["date"] = timezone.localdate()
        elif mode == self.Mode.LINK:
            tx = cleaned.get("existing_transaction")
            if not tx:
                self.add_error(
                    "existing_transaction",
                    _("Please select a transaction to link."),
                )
            elif tx.type != self.tx_type or tx.account.currency_id != self.event.currency_id:
                self.add_error(
                    "existing_transaction",
                    _("Pick a %(type)s in %(currency)s.")
                    % {
                        "type": Transaction.Type(self.tx_type).label.lower(),
                        "currency": self.event.currency.name,
                    },
                )
        return cleaned


class ExternalAuthForm(forms.Form):
    participant = forms.ModelChoiceField(
        queryset=SplitParticipant.objects.none(),
        label=_("Who are you?"),
    )
    username = forms.CharField(
        max_length=150,
        required=False,
        label=_("Username / nickname (optional)"),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
        min_length=4,
        label=_("Password"),
    )
    password_confirm = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        required=False,
        label=_("Confirm password"),
    )

    def __init__(self, *args, event: SplitEvent, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event
        self.fields["participant"].queryset = event.participants.filter(
            is_external=True,
            is_active=True,
        ).order_by("name", "id")

    def clean(self):
        cleaned = super().clean()
        participant: SplitParticipant | None = cleaned.get("participant")
        password = cleaned.get("password") or ""
        password_confirm = cleaned.get("password_confirm") or ""

        if not participant:
            return cleaned

        if participant.is_claimed:
            if not participant.check_external_password(password):
                self.add_error("password", _("Incorrect password."))
        else:
            if len(password) < 4:
                self.add_error(
                    "password", _("Password must be at least 4 characters long.")
                )
            elif password != password_confirm:
                self.add_error("password_confirm", _("Passwords do not match."))
        return cleaned
