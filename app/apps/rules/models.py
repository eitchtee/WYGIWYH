from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.common.models import SharedObject, SharedObjectManager


class TransactionRule(SharedObject):
    active = models.BooleanField(default=True)
    on_update = models.BooleanField(default=False)
    on_create = models.BooleanField(default=True)
    name = models.CharField(max_length=100, verbose_name=_("Name"))
    description = models.TextField(blank=True, null=True, verbose_name=_("Description"))
    trigger = models.TextField(verbose_name=_("Trigger"))

    objects = SharedObjectManager()
    all_objects = models.Manager()  # Unfiltered manager

    class Meta:
        verbose_name = _("Transaction rule")
        verbose_name_plural = _("Transaction rules")

    def __str__(self):
        return self.name


class TransactionRuleAction(models.Model):
    class Field(models.TextChoices):
        account = "account", _("Account")
        type = "type", _("Type")
        is_paid = "is_paid", _("Paid")
        date = "date", _("Date")
        reference_date = "reference_date", _("Reference Date")
        amount = "amount", _("Amount")
        description = "description", _("Description")
        notes = "notes", _("Notes")
        category = "category", _("Category")
        tags = "tags", _("Tags")
        entities = "entities", _("Entities")

    rule = models.ForeignKey(
        TransactionRule,
        on_delete=models.CASCADE,
        related_name="transaction_actions",
        verbose_name=_("Rule"),
    )
    field = models.CharField(
        max_length=50,
        choices=Field,
        verbose_name=_("Field"),
    )
    value = models.TextField(verbose_name=_("Value"))

    def __str__(self):
        return f"{self.rule} - {self.field} - {self.value}"

    class Meta:
        verbose_name = _("Edit transaction action")
        verbose_name_plural = _("Edit transaction actions")
        unique_together = (("rule", "field"),)


class UpdateOrCreateTransactionRuleAction(models.Model):
    """
    Will attempt to find and update latest matching transaction, or create new if none found.
    """

    class SearchOperator(models.TextChoices):
        EXACT = "exact", _("is exactly")
        CONTAINS = "contains", _("contains")
        STARTSWITH = "startswith", _("starts with")
        ENDSWITH = "endswith", _("ends with")
        EQ = "eq", _("equals")
        GT = "gt", _("greater than")
        LT = "lt", _("less than")
        GTE = "gte", _("greater than or equal")
        LTE = "lte", _("less than or equal")

    rule = models.ForeignKey(
        TransactionRule,
        on_delete=models.CASCADE,
        related_name="update_or_create_transaction_actions",
        verbose_name=_("Rule"),
    )

    filter = models.TextField(
        verbose_name=_("Filter"),
        blank=True,
        help_text=_(
            "Generic expression to enable or disable execution. Should evaluate to True or False"
        ),
    )

    # Search fields with operators
    search_account = models.TextField(
        verbose_name="Search Account",
        blank=True,
    )
    search_account_operator = models.CharField(
        max_length=10,
        choices=SearchOperator.choices,
        default=SearchOperator.EXACT,
        verbose_name="Account Operator",
    )

    search_type = models.TextField(
        verbose_name="Search Type",
        blank=True,
    )
    search_type_operator = models.CharField(
        max_length=10,
        choices=SearchOperator.choices,
        default=SearchOperator.EXACT,
        verbose_name="Type Operator",
    )

    search_is_paid = models.TextField(
        verbose_name="Search Is Paid",
        blank=True,
    )
    search_is_paid_operator = models.CharField(
        max_length=10,
        choices=SearchOperator.choices,
        default=SearchOperator.EXACT,
        verbose_name="Is Paid Operator",
    )

    search_date = models.TextField(
        verbose_name="Search Date",
        blank=True,
        help_text="Expression to match transaction date",
    )
    search_date_operator = models.CharField(
        max_length=10,
        choices=SearchOperator.choices,
        default=SearchOperator.EXACT,
        verbose_name="Date Operator",
    )

    search_reference_date = models.TextField(
        verbose_name="Search Reference Date",
        blank=True,
    )
    search_reference_date_operator = models.CharField(
        max_length=10,
        choices=SearchOperator.choices,
        default=SearchOperator.EXACT,
        verbose_name="Reference Date Operator",
    )

    search_amount = models.TextField(
        verbose_name="Search Amount",
        blank=True,
    )
    search_amount_operator = models.CharField(
        max_length=10,
        choices=SearchOperator.choices,
        default=SearchOperator.EXACT,
        verbose_name="Amount Operator",
    )

    search_description = models.TextField(
        verbose_name="Search Description",
        blank=True,
    )
    search_description_operator = models.CharField(
        max_length=10,
        choices=SearchOperator.choices,
        default=SearchOperator.CONTAINS,
        verbose_name="Description Operator",
    )

    search_notes = models.TextField(
        verbose_name="Search Notes",
        blank=True,
    )
    search_notes_operator = models.CharField(
        max_length=10,
        choices=SearchOperator.choices,
        default=SearchOperator.CONTAINS,
        verbose_name="Notes Operator",
    )

    search_category = models.TextField(
        verbose_name="Search Category",
        blank=True,
    )
    search_category_operator = models.CharField(
        max_length=10,
        choices=SearchOperator.choices,
        default=SearchOperator.EXACT,
        verbose_name="Category Operator",
    )

    search_tags = models.TextField(
        verbose_name="Search Tags",
        blank=True,
    )
    search_tags_operator = models.CharField(
        max_length=10,
        choices=SearchOperator.choices,
        default=SearchOperator.CONTAINS,
        verbose_name="Tags Operator",
    )

    search_entities = models.TextField(
        verbose_name="Search Entities",
        blank=True,
    )
    search_entities_operator = models.CharField(
        max_length=10,
        choices=SearchOperator.choices,
        default=SearchOperator.CONTAINS,
        verbose_name="Entities Operator",
    )

    search_internal_note = models.TextField(
        verbose_name="Search Internal Note",
        blank=True,
    )
    search_internal_note_operator = models.CharField(
        max_length=10,
        choices=SearchOperator.choices,
        default=SearchOperator.EXACT,
        verbose_name="Internal Note Operator",
    )

    search_internal_id = models.TextField(
        verbose_name="Search Internal ID",
        blank=True,
    )
    search_internal_id_operator = models.CharField(
        max_length=10,
        choices=SearchOperator.choices,
        default=SearchOperator.EXACT,
        verbose_name="Internal ID Operator",
    )

    # Set fields
    set_account = models.TextField(
        verbose_name=_("Account"),
        blank=True,
    )
    set_type = models.TextField(
        verbose_name=_("Type"),
        blank=True,
    )
    set_is_paid = models.TextField(
        verbose_name=_("Paid"),
        blank=True,
    )
    set_date = models.TextField(
        verbose_name=_("Date"),
        blank=True,
    )
    set_reference_date = models.TextField(
        verbose_name=_("Reference Date"),
        blank=True,
    )
    set_amount = models.TextField(
        verbose_name=_("Amount"),
        blank=True,
    )
    set_description = models.TextField(
        verbose_name=_("Description"),
        blank=True,
    )
    set_notes = models.TextField(
        verbose_name=_("Notes"),
        blank=True,
    )
    set_internal_note = models.TextField(
        verbose_name=_("Internal Note"),
        blank=True,
    )
    set_internal_id = models.TextField(
        verbose_name=_("Internal ID"),
        blank=True,
    )
    set_entities = models.TextField(
        verbose_name=_("Entities"),
        blank=True,
    )
    set_category = models.TextField(
        verbose_name=_("Category"),
        blank=True,
    )
    set_tags = models.TextField(
        verbose_name=_("Tags"),
        blank=True,
    )

    class Meta:
        verbose_name = _("Update or create transaction action")
        verbose_name_plural = _("Update or create transaction actions")

    def __str__(self):
        return f"Update or create transaction action for {self.rule}"

    def build_search_query(self, simple):
        """Builds Q objects based on search fields and their operators"""
        search_query = Q()

        def add_to_query(field_name, value, operator):
            lookup = f"{field_name}__{operator}"
            return Q(**{lookup: value})

        if self.search_account:
            value = simple.eval(self.search_account)
            if isinstance(value, int):
                search_query &= add_to_query(
                    "account_id", value, self.search_account_operator
                )
            else:
                search_query &= add_to_query(
                    "account__name", value, self.search_account_operator
                )

        if self.search_type:
            value = simple.eval(self.search_type)
            search_query &= add_to_query("type", value, self.search_type_operator)

        if self.search_is_paid:
            value = simple.eval(self.search_is_paid)
            search_query &= add_to_query("is_paid", value, self.search_is_paid_operator)

        if self.search_date:
            value = simple.eval(self.search_date)
            search_query &= add_to_query("date", value, self.search_date_operator)

        if self.search_reference_date:
            value = simple.eval(self.search_reference_date)
            search_query &= add_to_query(
                "reference_date", value, self.search_reference_date_operator
            )

        if self.search_amount:
            value = simple.eval(self.search_amount)
            search_query &= add_to_query("amount", value, self.search_amount_operator)

        if self.search_description:
            value = simple.eval(self.search_description)
            search_query &= add_to_query(
                "description", value, self.search_description_operator
            )

        if self.search_notes:
            value = simple.eval(self.search_notes)
            search_query &= add_to_query("notes", value, self.search_notes_operator)

        if self.search_internal_note:
            value = simple.eval(self.search_internal_note)
            search_query &= add_to_query(
                "internal_note", value, self.search_internal_note_operator
            )

        if self.search_internal_id:
            value = simple.eval(self.search_internal_id)
            search_query &= add_to_query(
                "internal_id", value, self.search_internal_id_operator
            )

        if self.search_category:
            value = simple.eval(self.search_category)
            if isinstance(value, int):
                search_query &= add_to_query(
                    "category_id", value, self.search_category_operator
                )
            else:
                search_query &= add_to_query(
                    "category__name", value, self.search_category_operator
                )

        if self.search_tags:
            tags_value = simple.eval(self.search_tags)
            if isinstance(tags_value, (list, tuple)):
                for tag in tags_value:
                    if isinstance(tag, int):
                        search_query &= Q(tags__id=tag)
                    else:
                        search_query &= Q(tags__name__iexact=tag)
            elif isinstance(tags_value, (int, str)):
                if isinstance(tags_value, int):
                    search_query &= Q(tags__id=tags_value)
                else:
                    search_query &= Q(tags__name__iexact=tags_value)

        if self.search_entities:
            entities_value = simple.eval(self.search_entities)
            if isinstance(entities_value, (list, tuple)):
                for entity in entities_value:
                    if isinstance(entity, int):
                        search_query &= Q(entities__id=entity)
                    else:
                        search_query &= Q(entities__name__iexact=entity)
            elif isinstance(entities_value, (int, str)):
                if isinstance(entities_value, int):
                    search_query &= Q(entities__id=entities_value)
                else:
                    search_query &= Q(entities__name__iexact=entities_value)

        return search_query
