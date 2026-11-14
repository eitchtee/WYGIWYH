from copy import deepcopy

from apps.accounts.models import Account
from apps.common.fields.forms.dynamic_select import (
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)
from apps.common.middleware.thread_local import get_current_user
from apps.common.widgets.crispy.daisyui import Switch
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.datepicker import AirDatePickerInput, AirMonthYearPickerInput
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput
from apps.common.widgets.tom_select import TomSelect
from apps.rules.signals import transaction_created, transaction_updated
from apps.transactions.models import (
    InstallmentPlan,
    TransactionAttachment,
    QuickTransaction,
    RecurringTransaction,
    SubTransaction,
    Transaction,
    TransactionCategory,
    TransactionEntity,
    TransactionTag,
)
from crispy_forms.bootstrap import AccordionGroup, AppendedText, FormActions, Accordion
from crispy_forms.helper import FormHelper
from crispy_forms.layout import (
    HTML,
    Column,
    Div,
    Field,
    Layout,
    Row,
)
from django import forms
from django.db import transaction as db_transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_file_clean(file, initial) for file in data]
        if data:
            return [single_file_clean(data, initial)]
        return []


class SubTransactionForm(forms.ModelForm):
    class Meta:
        model = SubTransaction
        fields = ["name", "amount"]
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "input join-item flex-1", "placeholder": _("Name")}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Built per request so the mask uses the user's number format
        self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput(
            attrs={
                "class": "input join-item w-2/5",
                "inputmode": "decimal",
                "placeholder": _("Amount"),
            }
        )


class SubTransactionsFormMixin:
    """Adds sub-transactions to a transaction or template form; while there are any,
    the amount field is their sum. Transfers don't take them.

    Rendered by transactions/widgets/sub_transactions.html, placed after the amount.
    """

    sub_amount_field = "amount"

    def __init__(self, *args, sub_transactions_initial=None, **kwargs):
        super().__init__(*args, **kwargs)
        data = self.data if self.is_bound else None
        if data is not None and "sub-TOTAL_FORMS" not in data:
            # Posts without the formset (e.g. shortcuts to /add/) leave sub-transactions alone
            data = {"sub-TOTAL_FORMS": "0", "sub-INITIAL_FORMS": "0"}
        initial = sub_transactions_initial or []
        self.sub_transactions = forms.inlineformset_factory(
            type(self.instance),
            SubTransaction,
            form=SubTransactionForm,
            extra=len(initial),
            can_delete=True,
        )(data, instance=self.instance, prefix="sub", initial=initial)
        # With sub-transactions the amount is their sum, see clean()
        self.fields[self.sub_amount_field].required = False

    def _takes_sub_transactions(self):
        return self.cleaned_data.get("type") != "TR"

    def clean(self):
        cleaned_data = super().clean()
        field = self.sub_amount_field
        if self._takes_sub_transactions() and self.sub_transactions.is_valid():
            amounts = [
                f.cleaned_data["amount"]
                for f in self.sub_transactions.forms
                if f.cleaned_data and not f.cleaned_data.get("DELETE")
            ]
            if amounts:
                cleaned_data[field] = sum(amounts)
        if cleaned_data.get(field) is None and field not in self.errors:
            self.add_error(field, self.fields[field].error_messages["required"])
        return cleaned_data

    def is_valid(self):
        return super().is_valid() and (
            not self._takes_sub_transactions() or self.sub_transactions.is_valid()
        )

    def save(self, *args, **kwargs):
        with db_transaction.atomic():
            instance = super().save(*args, **kwargs)
            if self._takes_sub_transactions():
                self.sub_transactions.instance = instance
                self.sub_transactions.save()
            else:
                instance.sub_transactions.all().delete()
        return instance


class TransactionForm(SubTransactionsFormMixin, forms.ModelForm):
    category = DynamicModelChoiceField(
        create_field="name",
        model=TransactionCategory,
        required=False,
        label=_("Category"),
        queryset=TransactionCategory.objects.filter(active=True),
    )
    tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
        queryset=TransactionTag.objects.filter(active=True),
    )
    entities = DynamicModelMultipleChoiceField(
        model=TransactionEntity,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Entities"),
    )
    account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_archived=False),
        label=_("Account"),
        widget=TomSelect(clear_button=False, group_by="group"),
    )

    date = forms.DateField(label=_("Date"))

    reference_date = forms.DateField(
        widget=AirMonthYearPickerInput(),
        label=_("Reference Date"),
        required=False,
    )

    class Meta:
        model = Transaction
        fields = [
            "account",
            "type",
            "is_paid",
            "date",
            "reference_date",
            "amount",
            "description",
            "notes",
            "category",
            "tags",
            "entities",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
            "account": TomSelect(clear_button=False, group_by="group"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # if editing a transaction display non-archived items and it's own item even if it's archived
        if self.instance.id:
            self.fields["account"].queryset = Account.objects.filter(
                Q(is_archived=False) | Q(transactions=self.instance.id),
            )

            self.fields["category"].queryset = TransactionCategory.objects.filter(
                Q(active=True) | Q(transaction=self.instance.id)
            )

            self.fields["tags"].queryset = TransactionTag.objects.filter(
                Q(active=True) | Q(transaction=self.instance.id)
            )

            self.fields["entities"].queryset = TransactionEntity.objects.filter(
                Q(active=True) | Q(transactions=self.instance.id)
            )
        else:
            self.fields["account"].queryset = Account.objects.filter(
                is_archived=False,
            )
            user_settings = get_current_user().settings
            if user_settings.default_account:
                self.fields["account"].initial = user_settings.default_account

            self.fields["category"].queryset = TransactionCategory.objects.filter(
                active=True
            )
            self.fields["tags"].queryset = TransactionTag.objects.filter(active=True)
            self.fields["entities"].queryset = TransactionEntity.objects.all()

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            Field(
                "type",
                template="transactions/widgets/income_expense_toggle_buttons.html",
            ),
            Field("is_paid", template="transactions/widgets/paid_toggle_button.html"),
            Row(
                Column("account"),
                Column("entities"),
            ),
            Row(
                Column(Field("date")),
                Column(Field("reference_date")),
            ),
            "description",
            Field("amount", inputmode="decimal"),
            HTML('{% include "transactions/widgets/sub_transactions.html" %}'),
            Row(
                Column("category"),
                Column("tags"),
            ),
            "notes",
        )

        self.helper_simple = FormHelper()
        self.helper_simple.form_tag = False
        self.helper_simple.form_method = "post"
        self.helper_simple.layout = Layout(
            Field(
                "type",
                template="transactions/widgets/income_expense_toggle_buttons.html",
            ),
            Field("is_paid", template="transactions/widgets/paid_toggle_button.html"),
            "account",
            Row(
                Column(Field("date")),
                Column(Field("reference_date")),
            ),
            "description",
            Field("amount", inputmode="decimal"),
            HTML('{% include "transactions/widgets/sub_transactions.html" %}'),
            Accordion(
                AccordionGroup(
                    _("More"),
                    "entities",
                    Row(
                        Column("category"),
                        Column("tags"),
                    ),
                    "notes",
                    active=False,
                ),
                flush=False,
                always_open=False,
                css_class="mb-3",
            ),
            FormActions(
                NoClassSubmit("submit", _("Add"), css_class="btn btn-primary"),
            ),
        )

        self.fields["date"].widget = AirDatePickerInput(clear_button=False)

        if self.instance and self.instance.pk:
            decimal_places = self.instance.account.currency.decimal_places
            self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput(
                decimal_places=decimal_places
            )
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Update"), css_class="btn btn-primary"),
                ),
            )
        else:
            self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput()
            self.helper.layout.append(
                Div(
                    NoClassSubmit("submit", _("Add"), css_class="btn btn-primary"),
                    NoClassSubmit(
                        "submit_and_similar",
                        _("Save and add similar"),
                        css_class="btn btn-primary btn-soft",
                    ),
                    NoClassSubmit(
                        "submit_and_another",
                        _("Save and add another"),
                        css_class="btn btn-primary btn-soft",
                    ),
                    css_class="flex flex-col gap-2 mt-3",
                ),
            )

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get("date")
        reference_date = cleaned_data.get("reference_date")

        if date and not reference_date:
            cleaned_data["reference_date"] = date.replace(day=1)

        return cleaned_data

    def save(self, **kwargs):
        is_new = not self.instance.id

        if not is_new:
            old_data = deepcopy(Transaction.objects.get(pk=self.instance.id))
        else:
            old_data = None

        instance = super().save(**kwargs)
        if is_new:
            transaction_created.send(sender=instance)
        else:
            transaction_updated.send(sender=instance, old_data=old_data)

        return instance


class TransactionAttachmentForm(forms.Form):
    attachments = MultipleFileField(
        required=True,
        label=_("Attachments"),
        help_text=_("Files are private and only visible to users with access to this transaction."),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "attachments",
            FormActions(
                NoClassSubmit("submit", _("Upload"), css_class="btn btn-primary"),
            ),
        )

    def save(self, transaction, uploaded_by):
        created = []
        for attachment in self.cleaned_data.get("attachments") or []:
            created.append(
                TransactionAttachment.objects.create(
                    transaction=transaction,
                    file=attachment,
                    original_name=attachment.name,
                    content_type=getattr(attachment, "content_type", ""),
                    size=attachment.size,
                    uploaded_by=uploaded_by,
                )
            )
        return created


def _transfer_fields(form):
    """To account/To amount for recurring and quick transfers, shown only for the Transfer type."""
    form.fields["to_account"].queryset = Account.objects.filter(
        Q(is_archived=False) | Q(pk=form.instance.to_account_id)
    )
    form.fields["to_amount"].widget = ArbitraryDecimalDisplayNumberInput()
    return Div(
        Row(Column("to_account"), Column("to_amount")),
        x_show="type === 'TR'",
        x_cloak="",
    )


def _type_aware(form, *layout):
    """Wraps a layout so it knows the selected type (used by _transfer_fields)."""
    return Div(
        *layout,
        x_data="{ type: '%s' }" % (form["type"].value() or ""),
        **{"x-on:change": "if ($event.target.name === 'type') type = $event.target.value"},
    )


class QuickTransactionForm(SubTransactionsFormMixin, forms.ModelForm):
    category = DynamicModelChoiceField(
        create_field="name",
        model=TransactionCategory,
        required=False,
        label=_("Category"),
        queryset=TransactionCategory.objects.filter(active=True),
    )
    tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
        queryset=TransactionTag.objects.filter(active=True),
    )
    entities = DynamicModelMultipleChoiceField(
        model=TransactionEntity,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Entities"),
    )
    account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_archived=False),
        label=_("Account"),
        widget=TomSelect(clear_button=False, group_by="group"),
    )
    to_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_archived=False),
        label=_("To account"),
        widget=TomSelect(clear_button=False, group_by="group"),
        required=False,
    )

    class Meta:
        model = QuickTransaction
        fields = [
            "name",
            "account",
            "type",
            "is_paid",
            "amount",
            "to_account",
            "to_amount",
            "description",
            "notes",
            "category",
            "tags",
            "entities",
            "mute",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
            "account": TomSelect(clear_button=False, group_by="group"),
        }
        help_texts = {
            "mute": _("Muted transactions won't be displayed on monthly summaries")
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # if editing a transaction display non-archived items and it's own item even if it's archived
        if self.instance.id:
            self.fields["account"].queryset = Account.objects.filter(
                Q(is_archived=False) | Q(transactions=self.instance.id),
            )

            self.fields["category"].queryset = TransactionCategory.objects.filter(
                Q(active=True) | Q(transaction=self.instance.id)
            )

            self.fields["tags"].queryset = TransactionTag.objects.filter(
                Q(active=True) | Q(transaction=self.instance.id)
            )

            self.fields["entities"].queryset = TransactionEntity.objects.filter(
                Q(active=True) | Q(transactions=self.instance.id)
            )
        else:
            self.fields["account"].queryset = Account.objects.filter(
                is_archived=False,
            )

            self.fields["category"].queryset = TransactionCategory.objects.filter(
                active=True
            )
            self.fields["tags"].queryset = TransactionTag.objects.filter(active=True)
            self.fields["entities"].queryset = TransactionEntity.objects.all()

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            _type_aware(
                self,
                Field(
                    "type",
                    template="transactions/widgets/income_expense_toggle_buttons.html",
                ),
                Field("is_paid", template="transactions/widgets/paid_toggle_button.html"),
                "name",
                HTML('<hr class="hr my-3" />'),
                Row(
                    Column("account"),
                    Column("entities"),
                ),
                "description",
                Field("amount", inputmode="decimal"),
                HTML('{% include "transactions/widgets/sub_transactions.html" %}'),
                _transfer_fields(self),
                Row(
                    Column("category"),
                    Column("tags"),
                ),
                "notes",
                Switch("mute"),
            )
        )

        if self.instance and self.instance.pk:
            decimal_places = self.instance.account.currency.decimal_places
            self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput(
                decimal_places=decimal_places
            )
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Update"), css_class="btn btn-primary"),
                ),
            )
        else:
            self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput()
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Add"), css_class="btn btn-primary"),
                ),
            )


class BulkEditTransactionForm(forms.Form):
    type = forms.ChoiceField(
        choices=(Transaction.Type.choices),
        required=False,
        label=_("Type"),
    )
    is_paid = forms.NullBooleanField(
        required=False,
        label=_("Paid"),
    )
    account = DynamicModelChoiceField(
        model=Account,
        required=False,
        label=_("Account"),
        queryset=Account.objects.filter(is_archived=False),
        widget=TomSelect(clear_button=False, group_by="group"),
    )
    date = forms.DateField(
        label=_("Date"),
        required=False,
        widget=AirDatePickerInput(clear_button=False),
    )
    reference_date = forms.DateField(
        widget=AirMonthYearPickerInput(),
        label=_("Reference Date"),
        required=False,
    )
    amount = forms.DecimalField(
        max_digits=42,
        decimal_places=30,
        required=False,
        label=_("Amount"),
        widget=ArbitraryDecimalDisplayNumberInput(),
    )
    description = forms.CharField(
        max_length=500, required=False, label=_("Description")
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label=_("Notes"),
    )
    category = DynamicModelChoiceField(
        create_field="name",
        model=TransactionCategory,
        required=False,
        label=_("Category"),
        queryset=TransactionCategory.objects.filter(active=True),
    )
    tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
        queryset=TransactionTag.objects.filter(active=True),
    )
    entities = DynamicModelMultipleChoiceField(
        model=TransactionEntity,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Entities"),
        queryset=TransactionEntity.objects.all(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["account"].queryset = Account.objects.filter(
            is_archived=False,
        )

        self.fields["category"].queryset = TransactionCategory.objects.filter(
            active=True
        )
        self.fields["tags"].queryset = TransactionTag.objects.filter(active=True)
        self.fields["entities"].queryset = TransactionEntity.objects.all()

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            Field(
                "type",
                template="transactions/widgets/unselectable_income_expense_toggle_buttons.html",
            ),
            Field(
                "is_paid",
                template="transactions/widgets/unselectable_paid_toggle_button.html",
            ),
            Row(
                Column("account"),
                Column("entities"),
            ),
            Row(
                Column(Field("date")),
                Column(Field("reference_date")),
            ),
            "description",
            Field("amount", inputmode="decimal"),
            Row(
                Column("category"),
                Column("tags"),
            ),
            "notes",
            FormActions(
                NoClassSubmit("submit", _("Update"), css_class="btn btn-primary"),
            ),
        )

        self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["date"].widget = AirDatePickerInput(clear_button=False)


class TransferForm(forms.Form):
    from_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_archived=False),
        label=_("From Account"),
        widget=TomSelect(clear_button=False, group_by="group"),
    )
    to_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_archived=False),
        label=_("To Account"),
        widget=TomSelect(clear_button=False, group_by="group"),
    )

    from_amount = forms.DecimalField(
        max_digits=42,
        decimal_places=30,
        label=_("From Amount"),
    )
    to_amount = forms.DecimalField(
        max_digits=42,
        decimal_places=30,
        label=_("To Amount"),
        required=False,
    )

    from_category = DynamicModelChoiceField(
        create_field="name",
        model=TransactionCategory,
        required=False,
        label=_("Category"),
        queryset=TransactionCategory.objects.filter(active=True),
    )
    to_category = DynamicModelChoiceField(
        create_field="name",
        model=TransactionCategory,
        required=False,
        label=_("Category"),
        queryset=TransactionCategory.objects.filter(active=True),
    )

    from_tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
        queryset=TransactionTag.objects.filter(active=True),
    )
    to_tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
        queryset=TransactionTag.objects.filter(active=True),
    )

    from_entities = DynamicModelMultipleChoiceField(
        model=TransactionEntity,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Entities"),
    )
    to_entities = DynamicModelMultipleChoiceField(
        model=TransactionEntity,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Entities"),
    )

    is_paid = forms.BooleanField(label=_("Paid"), initial=True, required=False)

    date = forms.DateField(label=_("Date"))

    reference_date = forms.DateField(
        widget=AirMonthYearPickerInput(), label=_("Reference Date"), required=False
    )

    description = forms.CharField(
        max_length=500, label=_("Description"), required=False
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
            }
        ),
        label=_("Notes"),
    )

    mute = forms.BooleanField(
        label=_("Mute"),
        initial=True,
        required=False,
        help_text=_("Muted transactions won't be displayed on monthly summaries"),
    )

    def __init__(self, *args, instance=None, **kwargs):
        # instance: either side of an existing transfer, to edit it
        self.instance = instance
        if instance:
            from_t, to_t = instance.transfer_from, instance.transfer_to
            kwargs["initial"] = {
                "from_account": from_t.account,
                "to_account": to_t.account,
                "from_amount": from_t.amount,
                "to_amount": to_t.amount,
                "from_category": from_t.category,
                "to_category": to_t.category,
                "from_tags": list(from_t.tags.all()),
                "to_tags": list(to_t.tags.all()),
                "from_entities": list(from_t.entities.all()),
                "to_entities": list(to_t.entities.all()),
                "date": from_t.date,
                "reference_date": from_t.reference_date,
                "description": from_t.description,
                "notes": from_t.notes,
                "mute": from_t.mute,
                "is_paid": from_t.is_paid,
            }
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"

        self.helper.layout = Layout(
            Field("is_paid", template="transactions/widgets/paid_toggle_button.html"),
            Row(
                Column(Field("date")),
                Column(
                    Field("reference_date"),
                ),
            ),
            Field("description"),
            Field("notes"),
            Switch("mute"),
            Row(
                Column("from_account"),
                Column(Field("from_amount")),
                Column("from_category"),
                Column("from_tags"),
                Column("from_entities"),
                css_class="bg-base-100 rounded-box p-4 border-base-content/60 border my-3",
            ),
            Row(
                Column(
                    "to_account",
                ),
                Column(
                    Field("to_amount"),
                ),
                Column("to_category"),
                Column("to_tags"),
                Column("to_entities"),
                css_class="bg-base-100 rounded-box p-4 border-base-content/60 border",
            ),
            FormActions(
                NoClassSubmit(
                    "submit",
                    _("Update") if instance else _("Transfer"),
                    css_class="btn btn-primary",
                ),
            ),
        )

        self.fields["from_amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["to_amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["date"].widget = AirDatePickerInput(clear_button=False)

        # When editing, keep the transfer's own archived/inactive items selectable,
        # like TransactionForm does, so saving doesn't drop them.
        own = (
            [instance.transfer_from.pk, instance.transfer_to.pk] if instance else []
        )
        accounts = Account.objects.filter(
            Q(is_archived=False) | Q(transactions__in=own)
        ).distinct()
        categories = TransactionCategory.objects.filter(
            Q(active=True) | Q(transaction__in=own)
        ).distinct()
        tags = TransactionTag.objects.filter(
            Q(active=True) | Q(transaction__in=own)
        ).distinct()
        entities = TransactionEntity.objects.filter(
            Q(active=True) | Q(transactions__in=own)
        ).distinct()
        for side in ("from", "to"):
            self.fields[f"{side}_account"].queryset = accounts
            self.fields[f"{side}_category"].queryset = categories
            self.fields[f"{side}_tags"].queryset = tags
            self.fields[f"{side}_entities"].queryset = entities

    def clean(self):
        cleaned_data = super().clean()
        from_account = cleaned_data.get("from_account")
        to_account = cleaned_data.get("to_account")

        if from_account == to_account:
            raise forms.ValidationError(_("From and To accounts must be different."))

        return cleaned_data

    def save(self):
        data = self.cleaned_data

        if self.instance:
            from_transaction = self.instance.transfer_from
            to_transaction = self.instance.transfer_to
            # Snapshots for update rules, taken before anything changes
            old_data = [
                deepcopy(Transaction.objects.get(pk=t.pk))
                for t in (from_transaction, to_transaction)
            ]
        else:
            from_transaction = Transaction(type=Transaction.Type.EXPENSE)
            to_transaction = Transaction(type=Transaction.Type.INCOME)

        for transaction, side in ((from_transaction, "from"), (to_transaction, "to")):
            transaction.account = data[f"{side}_account"]
            transaction.category = data.get(f"{side}_category")
            transaction.date = data["date"]
            transaction.reference_date = data["reference_date"]
            transaction.description = data["description"]
            transaction.notes = data.get("notes")
            transaction.mute = data["mute"]
            transaction.is_paid = data["is_paid"]
        from_transaction.amount = data["from_amount"]
        to_transaction.amount = data["to_amount"] or data["from_amount"]

        # Both sides get the shared fields here, so no partner sync (and its rule
        # signal) on save; the signals below cover each side once.
        with db_transaction.atomic():
            from_transaction.save(sync_partner=False)
            to_transaction.linked_transaction = from_transaction
            to_transaction.save(sync_partner=False)
            if not from_transaction.linked_transaction_id:
                from_transaction.linked_transaction = to_transaction
                from_transaction.save(sync_partner=False)

            from_transaction.tags.set(data.get("from_tags", []))
            to_transaction.tags.set(data.get("to_tags", []))
            from_transaction.entities.set(data.get("from_entities", []))
            to_transaction.entities.set(data.get("to_entities", []))

        # Rules run for each side, like any other transaction
        for i, transaction in enumerate((from_transaction, to_transaction)):
            if self.instance:
                transaction_updated.send(sender=transaction, old_data=old_data[i])
            else:
                transaction_created.send(sender=transaction)

        return from_transaction, to_transaction


class InstallmentPlanForm(SubTransactionsFormMixin, forms.ModelForm):
    sub_amount_field = "installment_amount"

    account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_archived=False),
        label=_("Account"),
        widget=TomSelect(clear_button=False, group_by="group"),
    )
    tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
        queryset=TransactionTag.objects.filter(active=True),
    )
    category = DynamicModelChoiceField(
        create_field="name",
        model=TransactionCategory,
        required=False,
        label=_("Category"),
        queryset=TransactionCategory.objects.filter(active=True),
    )
    entities = DynamicModelMultipleChoiceField(
        model=TransactionEntity,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Entities"),
        queryset=TransactionEntity.objects.filter(active=True),
    )
    type = forms.ChoiceField(choices=Transaction.Type.choices)

    reference_date = forms.DateField(
        widget=AirMonthYearPickerInput(), label=_("Reference Date"), required=False
    )

    class Meta:
        model = InstallmentPlan
        fields = [
            "type",
            "account",
            "start_date",
            "reference_date",
            "description",
            "number_of_installments",
            "recurrence",
            "installment_amount",
            "category",
            "tags",
            "notes",
            "installment_start",
            "entities",
            "add_description_to_transaction",
            "add_notes_to_transaction",
        ]
        widgets = {
            "account": TomSelect(),
            "recurrence": TomSelect(clear_button=False),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # if editing display non-archived items and it's own item even if it's archived
        if self.instance.id:
            self.fields["account"].queryset = Account.objects.filter(
                Q(is_archived=False) | Q(installmentplan=self.instance.id)
            ).distinct()

            self.fields["category"].queryset = TransactionCategory.objects.filter(
                Q(active=True) | Q(installmentplan=self.instance.id)
            ).distinct()

            self.fields["tags"].queryset = TransactionTag.objects.filter(
                Q(active=True) | Q(installmentplan=self.instance.id)
            ).distinct()

            self.fields["entities"].queryset = TransactionEntity.objects.filter(
                Q(active=True) | Q(installmentplan=self.instance.id)
            ).distinct()
        else:
            self.fields["account"].queryset = Account.objects.filter(is_archived=False)
            user_settings = get_current_user().settings
            if user_settings.default_account:
                self.fields["account"].initial = user_settings.default_account

            self.fields["category"].queryset = TransactionCategory.objects.filter(
                active=True
            )

            self.fields["tags"].queryset = TransactionTag.objects.filter(active=True)

            self.fields["entities"].queryset = TransactionEntity.objects.filter(
                active=True
            )

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"

        self.helper.layout = Layout(
            Field(
                "type",
                template="transactions/widgets/income_expense_toggle_buttons.html",
            ),
            Row(
                Column("account"),
                Column("entities"),
            ),
            "description",
            Switch("add_description_to_transaction"),
            "notes",
            Switch("add_notes_to_transaction"),
            Row(
                Column("number_of_installments"),
                Column("installment_start"),
            ),
            Row(
                Column("start_date", css_class="col-span-12 md:col-span-4"),
                Column("reference_date", css_class="col-span-12 md:col-span-4"),
                Column("recurrence", css_class="col-span-12 md:col-span-4"),
            ),
            "installment_amount",
            HTML('{% include "transactions/widgets/sub_transactions.html" %}'),
            Row(
                Column("category"),
                Column("tags"),
            ),
        )

        self.fields["installment_amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["start_date"].widget = AirDatePickerInput(clear_button=False)

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Update"), css_class="btn btn-primary"),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Add"), css_class="btn btn-primary"),
                ),
            )

    def save(self, source_transaction=None, **kwargs):
        is_new = not self.instance.id

        instance = super().save(**kwargs)
        if is_new and source_transaction:
            # The converted transaction becomes the first installment
            source_transaction.installment_plan = instance
            source_transaction.installment_id = instance.installment_start
            # Take the amount set on the form, even if already paid
            source_transaction.amount = instance.installment_amount
            source_transaction.save()
            source_transaction.copy_sub_transactions_from(instance)
            instance.update_transactions()
        elif is_new:
            instance.create_transactions()
        else:
            instance.update_transactions()

        return instance


class TransactionTagForm(forms.ModelForm):
    class Meta:
        model = TransactionTag
        fields = ["name", "active"]
        labels = {"name": _("Tag name")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(Field("name", css_class="mb-3"), Switch("active"))

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Update"), css_class="btn btn-primary"),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Add"), css_class="btn btn-primary"),
                ),
            )


class TransactionEntityForm(forms.ModelForm):
    class Meta:
        model = TransactionEntity
        fields = ["name", "active"]
        labels = {"name": _("Entity name")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(Field("name"), Switch("active"))

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Update"), css_class="btn btn-primary"),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Add"), css_class="btn btn-primary"),
                ),
            )


class TransactionCategoryForm(forms.ModelForm):
    class Meta:
        model = TransactionCategory
        fields = ["name", "mute", "active"]
        labels = {"name": _("Category name")}
        help_texts = {
            "mute": _("Muted categories won't be displayed on monthly summaries")
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(Field("name"), Switch("mute"), Switch("active"))

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Update"), css_class="btn btn-primary"),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Add"), css_class="btn btn-primary"),
                ),
            )


class RecurringTransactionForm(SubTransactionsFormMixin, forms.ModelForm):
    account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_archived=False),
        label=_("Account"),
        widget=TomSelect(clear_button=False, group_by="group"),
    )
    tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
        queryset=TransactionTag.objects.filter(active=True),
    )
    category = DynamicModelChoiceField(
        create_field="name",
        model=TransactionCategory,
        required=False,
        label=_("Category"),
        queryset=TransactionCategory.objects.filter(active=True),
    )
    entities = DynamicModelMultipleChoiceField(
        model=TransactionEntity,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Entities"),
        queryset=TransactionEntity.objects.filter(active=True),
    )
    type = forms.ChoiceField(choices=RecurringTransaction.Type.choices)
    to_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_archived=False),
        label=_("To account"),
        widget=TomSelect(clear_button=False, group_by="group"),
        required=False,
    )

    class Meta:
        model = RecurringTransaction
        fields = [
            "account",
            "type",
            "amount",
            "to_account",
            "to_amount",
            "description",
            "add_description_to_transaction",
            "category",
            "tags",
            "start_date",
            "reference_date",
            "end_date",
            "recurrence_type",
            "recurrence_interval",
            "notes",
            "add_notes_to_transaction",
            "entities",
            "keep_at_most",
        ]
        widgets = {
            "reference_date": AirMonthYearPickerInput(),
            "recurrence_type": TomSelect(clear_button=False),
            "notes": forms.Textarea(
                attrs={
                    "rows": 3,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # if editing display non-archived items and it's own item even if it's archived
        if self.instance.id:
            self.fields["account"].queryset = Account.objects.filter(
                Q(is_archived=False) | Q(recurringtransaction=self.instance.id)
            ).distinct()

            self.fields["category"].queryset = TransactionCategory.objects.filter(
                Q(active=True) | Q(recurringtransaction=self.instance.id)
            ).distinct()

            self.fields["tags"].queryset = TransactionTag.objects.filter(
                Q(active=True) | Q(recurringtransaction=self.instance.id)
            ).distinct()

            self.fields["entities"].queryset = TransactionEntity.objects.filter(
                Q(active=True) | Q(recurringtransaction=self.instance.id)
            ).distinct()
        else:
            self.fields["account"].queryset = Account.objects.filter(is_archived=False)
            
            user_settings = get_current_user().settings
            if user_settings.default_account:
                self.fields["account"].initial = user_settings.default_account

            self.fields["category"].queryset = TransactionCategory.objects.filter(
                active=True
            )

            self.fields["tags"].queryset = TransactionTag.objects.filter(active=True)

            self.fields["entities"].queryset = TransactionEntity.objects.filter(
                active=True
            )

        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_tag = False

        self.helper.layout = Layout(
            _type_aware(
                self,
                Field(
                    "type",
                    template="transactions/widgets/income_expense_toggle_buttons.html",
                ),
                Row(
                    Column("account"),
                    Column("entities"),
                ),
                "description",
                Switch("add_description_to_transaction"),
                "amount",
                HTML('{% include "transactions/widgets/sub_transactions.html" %}'),
                _transfer_fields(self),
                Row(
                    Column("category"),
                    Column("tags"),
                ),
                "notes",
                Switch("add_notes_to_transaction"),
                Row(
                    Column("start_date"),
                    Column("reference_date"),
                ),
                Row(
                    Column("recurrence_interval", css_class="col-span-12 md:col-span-4"),
                    Column("recurrence_type", css_class="col-span-12 md:col-span-4"),
                    Column("end_date", css_class="col-span-12 md:col-span-4"),
                ),
                AppendedText("keep_at_most", _("future transactions")),
            )
        )

        self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["start_date"].widget = AirDatePickerInput(clear_button=False)
        self.fields["end_date"].widget = AirDatePickerInput()

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Update"), css_class="btn btn-primary"),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Add"), css_class="btn btn-primary"),
                ),
            )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and start_date > end_date:
            raise forms.ValidationError(_("End date should be after the start date"))

        return cleaned_data

    def save(self, source_transaction=None, **kwargs):
        is_new = not self.instance.id

        instance = super().save(**kwargs)
        if is_new:
            instance.create_upcoming_transactions(first_transaction=source_transaction)
        else:
            instance.update_unpaid_transactions()
            instance.generate_upcoming_transactions()

        return instance
