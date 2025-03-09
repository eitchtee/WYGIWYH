from crispy_bootstrap5.bootstrap5 import Switch, BS5Accordion
from crispy_forms.bootstrap import FormActions, AccordionGroup
from crispy_forms.helper import FormHelper
from crispy_forms.layout import (
    Layout,
    Row,
    Column,
    Field,
)
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Account
from apps.common.fields.forms.dynamic_select import (
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.datepicker import AirDatePickerInput, AirMonthYearPickerInput
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput
from apps.common.widgets.tom_select import TomSelect
from apps.rules.signals import transaction_created, transaction_updated
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
    InstallmentPlan,
    RecurringTransaction,
    TransactionEntity,
)
from apps.common.middleware.thread_local import get_current_user


class TransactionForm(forms.ModelForm):
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
                Column("account", css_class="form-group col-md-6 mb-0"),
                Column("entities", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            Row(
                Column(Field("date"), css_class="form-group col-md-6 mb-0"),
                Column(Field("reference_date"), css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            "description",
            Field("amount", inputmode="decimal"),
            Row(
                Column("category", css_class="form-group col-md-6 mb-0"),
                Column("tags", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
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
                Column(Field("date"), css_class="form-group col-md-6 mb-0"),
                Column(Field("reference_date"), css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            "description",
            Field("amount", inputmode="decimal"),
            BS5Accordion(
                AccordionGroup(
                    _("More"),
                    "entities",
                    Row(
                        Column("category", css_class="form-group col-md-6 mb-0"),
                        Column("tags", css_class="form-group col-md-6 mb-0"),
                        css_class="form-row",
                    ),
                    "notes",
                    active=False,
                ),
                flush=False,
                always_open=False,
                css_class="mb-3",
            ),
            FormActions(
                NoClassSubmit(
                    "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                ),
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
                    NoClassSubmit(
                        "submit", _("Update"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )
        else:
            self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput()
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                    ),
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

        instance = super().save(**kwargs)
        if is_new:
            transaction_created.send(sender=instance)
        else:
            transaction_updated.send(sender=instance)

        return instance


class BulkEditTransactionForm(TransactionForm):
    is_paid = forms.NullBooleanField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields optional
        for field_name, field in self.fields.items():
            field.required = False

        del self.helper.layout[-1]  # Remove button
        del self.helper.layout[0:2]  # Remove type, is_paid field

        self.helper.layout.insert(
            0,
            Field(
                "type",
                template="transactions/widgets/unselectable_income_expense_toggle_buttons.html",
            ),
        )

        self.helper.layout.insert(
            1,
            Field(
                "is_paid",
                template="transactions/widgets/unselectable_paid_toggle_button.html",
            ),
        )

        self.helper.layout.append(
            FormActions(
                NoClassSubmit(
                    "submit", _("Update"), css_class="btn btn-outline-primary w-100"
                ),
            ),
        )


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"

        self.helper.layout = Layout(
            Row(
                Column(Field("date"), css_class="form-group col-md-6 mb-0"),
                Column(
                    Field("reference_date"),
                    css_class="form-group col-md-6 mb-0",
                ),
                css_class="form-row",
            ),
            Field("description"),
            Field("notes"),
            Row(
                Column(
                    Row(
                        Column(
                            "from_account",
                            css_class="form-group col-md-6 mb-0",
                        ),
                        Column(
                            Field("from_amount"),
                            css_class="form-group col-md-6 mb-0",
                        ),
                        css_class="form-row",
                    ),
                    Row(
                        Column("from_category", css_class="form-group col-md-6 mb-0"),
                        Column("from_tags", css_class="form-group col-md-6 mb-0"),
                        css_class="form-row",
                    ),
                ),
                css_class="p-1 mx-1 my-3 border rounded-3",
            ),
            Row(
                Column(
                    Row(
                        Column(
                            "to_account",
                            css_class="form-group col-md-6 mb-0",
                        ),
                        Column(
                            Field("to_amount"),
                            css_class="form-group col-md-6 mb-0",
                        ),
                        css_class="form-row",
                    ),
                    Row(
                        Column("to_category", css_class="form-group col-md-6 mb-0"),
                        Column("to_tags", css_class="form-group col-md-6 mb-0"),
                        css_class="form-row",
                    ),
                ),
                css_class="p-1 mx-1 my-3 border rounded-3",
            ),
            FormActions(
                NoClassSubmit(
                    "submit", _("Transfer"), css_class="btn btn-outline-primary w-100"
                ),
            ),
        )

        self.fields["from_amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["to_amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["date"].widget = AirDatePickerInput(clear_button=False)

        self.fields["from_account"].queryset = Account.objects.filter(
            is_archived=False,
        )

        self.fields["from_category"].queryset = TransactionCategory.objects.filter(
            active=True
        )
        self.fields["from_tags"].queryset = TransactionTag.objects.filter(active=True)

        self.fields["to_account"].queryset = Account.objects.filter(
            is_archived=False,
        )

        self.fields["to_category"].queryset = TransactionCategory.objects.filter(
            active=True
        )
        self.fields["to_tags"].queryset = TransactionTag.objects.filter(active=True)

    def clean(self):
        cleaned_data = super().clean()
        from_account = cleaned_data.get("from_account")
        to_account = cleaned_data.get("to_account")

        if from_account == to_account:
            raise forms.ValidationError(_("From and To accounts must be different."))

        return cleaned_data

    def save(self):
        from_account = self.cleaned_data["from_account"]
        to_account = self.cleaned_data["to_account"]
        from_amount = self.cleaned_data["from_amount"]
        to_amount = self.cleaned_data["to_amount"] or from_amount
        date = self.cleaned_data["date"]
        reference_date = self.cleaned_data["reference_date"]
        description = self.cleaned_data["description"]
        from_category = self.cleaned_data.get("from_category")
        to_category = self.cleaned_data.get("to_category")
        notes = self.cleaned_data.get("notes")

        # Create "From" transaction
        from_transaction = Transaction.objects.create(
            account=from_account,
            type=Transaction.Type.EXPENSE,
            is_paid=True,
            date=date,
            reference_date=reference_date,
            amount=from_amount,
            description=description,
            category=from_category,
            notes=notes,
        )
        from_transaction.tags.set(self.cleaned_data.get("from_tags", []))

        # Create "To" transaction
        to_transaction = Transaction.objects.create(
            account=to_account,
            type=Transaction.Type.INCOME,
            is_paid=True,
            date=date,
            reference_date=reference_date,
            amount=to_amount,
            description=description,
            category=to_category,
            notes=notes,
        )
        to_transaction.tags.set(self.cleaned_data.get("to_tags", []))

        return from_transaction, to_transaction


class InstallmentPlanForm(forms.ModelForm):
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
                Column("account", css_class="form-group col-md-6 mb-0"),
                Column("entities", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            "description",
            Switch("add_description_to_transaction"),
            "notes",
            Switch("add_notes_to_transaction"),
            Row(
                Column("number_of_installments", css_class="form-group col-md-6 mb-0"),
                Column("installment_start", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            Row(
                Column("start_date", css_class="form-group col-md-4 mb-0"),
                Column("reference_date", css_class="form-group col-md-4 mb-0"),
                Column("recurrence", css_class="form-group col-md-4 mb-0"),
                css_class="form-row",
            ),
            "installment_amount",
            Row(
                Column("category", css_class="form-group col-md-6 mb-0"),
                Column("tags", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
        )

        self.fields["installment_amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["start_date"].widget = AirDatePickerInput(clear_button=False)

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Update"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )

    def save(self, **kwargs):
        is_new = not self.instance.id

        instance = super().save(**kwargs)
        if is_new:
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
                    NoClassSubmit(
                        "submit", _("Update"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                    ),
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
                    NoClassSubmit(
                        "submit", _("Update"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )


class TransactionCategoryForm(forms.ModelForm):
    class Meta:
        model = TransactionCategory
        fields = ["name", "mute", "active"]
        labels = {"name": _("Category name")}
        help_texts = {
            "mute": _("Muted categories won't count towards your monthly total")
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
                    NoClassSubmit(
                        "submit", _("Update"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )


class RecurringTransactionForm(forms.ModelForm):
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

    class Meta:
        model = RecurringTransaction
        fields = [
            "account",
            "type",
            "amount",
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
            Field(
                "type",
                template="transactions/widgets/income_expense_toggle_buttons.html",
            ),
            Row(
                Column("account", css_class="form-group col-md-6 mb-0"),
                Column("entities", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            "description",
            Switch("add_description_to_transaction"),
            "amount",
            Row(
                Column("category", css_class="form-group col-md-6 mb-0"),
                Column("tags", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            "notes",
            Switch("add_notes_to_transaction"),
            Row(
                Column("start_date", css_class="form-group col-md-6 mb-0"),
                Column("reference_date", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            Row(
                Column("recurrence_interval", css_class="form-group col-md-4 mb-0"),
                Column("recurrence_type", css_class="form-group col-md-4 mb-0"),
                Column("end_date", css_class="form-group col-md-4 mb-0"),
                css_class="form-row",
            ),
        )

        self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["start_date"].widget = AirDatePickerInput(clear_button=False)
        self.fields["end_date"].widget = AirDatePickerInput()

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Update"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and start_date > end_date:
            raise forms.ValidationError(_("End date should be after the start date"))

        return cleaned_data

    def save(self, **kwargs):
        is_new = not self.instance.id

        instance = super().save(**kwargs)
        if is_new:
            instance.create_upcoming_transactions()
        else:
            instance.update_unpaid_transactions()

        return instance
