from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from typing import Dict, List, TypedDict


class SankeyNode(TypedDict):
    name: str


class SankeyFlow(TypedDict):
    from_node: str
    to_node: str
    flow: float
    currency: Dict
    original_amount: float
    percentage: float


def generate_sankey_data_by_account(transactions_queryset):
    """
    Generates Sankey diagram data from transaction queryset using account as intermediary.
    """
    nodes: Dict[str, Dict] = {}
    flows: List[SankeyFlow] = []

    # Aggregate transactions
    income_data = {}  # {(category, currency, account) -> amount}
    expense_data = {}  # {(category, currency, account) -> amount}
    total_income_by_currency = {}  # {currency -> amount}
    total_expense_by_currency = {}  # {currency -> amount}
    total_volume_by_currency = {}  # {currency -> amount}

    for transaction in transactions_queryset:
        currency = transaction.account.currency
        account = transaction.account
        category = transaction.category or _("Uncategorized")
        key = (category, currency, account)
        amount = transaction.amount

        if transaction.type == "IN":
            income_data[key] = income_data.get(key, Decimal("0")) + amount
            total_income_by_currency[currency] = (
                total_income_by_currency.get(currency, Decimal("0")) + amount
            )
        else:
            expense_data[key] = expense_data.get(key, Decimal("0")) + amount
            total_expense_by_currency[currency] = (
                total_expense_by_currency.get(currency, Decimal("0")) + amount
            )

        total_volume_by_currency[currency] = (
            total_volume_by_currency.get(currency, Decimal("0")) + amount
        )

    unique_accounts = {
        account_id: idx
        for idx, account_id in enumerate(
            transactions_queryset.values_list("account", flat=True).distinct()
        )
    }

    def get_node_priority(node_id: str) -> int:
        """Get priority based on the account ID embedded in the node ID."""
        account_id = int(node_id.split("_")[-1])
        return unique_accounts[account_id]

    def get_node_id(node_type: str, name: str, account_id: int) -> str:
        """Generate unique node ID."""
        return f"{node_type}_{name}_{account_id}".lower().replace(" ", "_")

    def add_node(node_id: str, display_name: str) -> None:
        """Add node with ID, display name and priority."""
        nodes[node_id] = {
            "id": node_id,
            "name": display_name,
            "priority": get_node_priority(node_id),
        }

    def add_flow(
        from_node_id: str, to_node_id: str, amount: Decimal, currency, is_income: bool
    ) -> None:
        """
        Add flow with percentage based on total transaction volume for the specific currency.
        """
        total_volume = total_volume_by_currency.get(currency, Decimal("0"))
        percentage = (amount / total_volume) * 100 if total_volume else 0
        scaled_flow = percentage / 100

        flows.append(
            {
                "from_node": from_node_id,
                "to_node": to_node_id,
                "flow": float(scaled_flow),
                "currency": {
                    "code": currency.code,
                    "prefix": currency.prefix,
                    "suffix": currency.suffix,
                    "decimal_places": currency.decimal_places,
                },
                "original_amount": float(amount),
                "percentage": float(percentage),
            }
        )

    # Process income
    for (category, currency, account), amount in income_data.items():
        category_node_id = get_node_id("income", category, account.id)
        account_node_id = get_node_id("account", account.name, account.id)
        add_node(category_node_id, str(category))
        add_node(account_node_id, account.name)
        add_flow(category_node_id, account_node_id, amount, currency, is_income=True)

    # Process expenses
    for (category, currency, account), amount in expense_data.items():
        category_node_id = get_node_id("expense", category, account.id)
        account_node_id = get_node_id("account", account.name, account.id)
        add_node(category_node_id, str(category))
        add_node(account_node_id, account.name)
        add_flow(account_node_id, category_node_id, amount, currency, is_income=False)

    # Calculate and add savings flows
    savings_data = {}  # {(account, currency) -> amount}
    for (category, currency, account), amount in income_data.items():
        key = (account, currency)
        savings_data[key] = savings_data.get(key, Decimal("0")) + amount
    for (category, currency, account), amount in expense_data.items():
        key = (account, currency)
        savings_data[key] = savings_data.get(key, Decimal("0")) - amount

    for (account, currency), amount in savings_data.items():
        if amount > 0:
            account_node_id = get_node_id("account", account.name, account.id)
            savings_node_id = get_node_id("savings", _("Saved"), account.id)
            add_node(savings_node_id, str(_("Saved")))
            add_flow(account_node_id, savings_node_id, amount, currency, is_income=True)

    # Calculate total across all currencies (for reference only)
    total_amount = sum(float(amount) for amount in total_income_by_currency.values())

    return {
        "nodes": list(nodes.values()),
        "flows": flows,
        "total_amount": total_amount,
        "total_by_currency": {
            curr.code: float(amount)
            for curr, amount in total_income_by_currency.items()
        },
    }


def generate_sankey_data_by_currency(transactions_queryset):
    """
    Generates Sankey diagram data from transaction queryset, using currency as intermediary.
    """
    nodes: Dict[str, Dict] = {}
    flows: List[SankeyFlow] = []

    # Aggregate transactions
    income_data = {}  # {(category, currency) -> amount}
    expense_data = {}  # {(category, currency) -> amount}
    total_income_by_currency = {}  # {currency -> amount}
    total_expense_by_currency = {}  # {currency -> amount}
    total_volume_by_currency = {}  # {currency -> amount}

    for transaction in transactions_queryset:
        currency = transaction.account.currency
        category = transaction.category or _("Uncategorized")
        key = (category, currency)
        amount = transaction.amount

        if transaction.type == "IN":
            income_data[key] = income_data.get(key, Decimal("0")) + amount
            total_income_by_currency[currency] = (
                total_income_by_currency.get(currency, Decimal("0")) + amount
            )
        else:
            expense_data[key] = expense_data.get(key, Decimal("0")) + amount
            total_expense_by_currency[currency] = (
                total_expense_by_currency.get(currency, Decimal("0")) + amount
            )

        total_volume_by_currency[currency] = (
            total_volume_by_currency.get(currency, Decimal("0")) + amount
        )

    unique_currencies = {
        currency_id: idx
        for idx, currency_id in enumerate(
            transactions_queryset.values_list("account__currency", flat=True).distinct()
        )
    }

    def get_node_priority(node_id: str) -> int:
        """Get priority based on the currency ID embedded in the node ID."""
        currency_id = int(node_id.split("_")[-1])
        return unique_currencies[currency_id]

    def get_node_id(node_type: str, name: str, currency_id: int) -> str:
        """Generate unique node ID including currency information."""
        return f"{node_type}_{name}_{currency_id}".lower().replace(" ", "_")

    def add_node(node_id: str, display_name: str) -> None:
        """Add node with ID, display name and priority."""
        nodes[node_id] = {
            "id": node_id,
            "name": display_name,
            "priority": get_node_priority(node_id),
        }

    def add_flow(
        from_node_id: str, to_node_id: str, amount: Decimal, currency, is_income: bool
    ) -> None:
        """
        Add flow with percentage based on total transaction volume for the specific currency.
        """
        total_volume = total_volume_by_currency.get(currency, Decimal("0"))
        percentage = (amount / total_volume) * 100 if total_volume else 0
        scaled_flow = percentage / 100

        flows.append(
            {
                "from_node": from_node_id,
                "to_node": to_node_id,
                "flow": float(scaled_flow),
                "currency": {
                    "code": currency.code,
                    "name": currency.name,
                    "prefix": currency.prefix,
                    "suffix": currency.suffix,
                    "decimal_places": currency.decimal_places,
                },
                "original_amount": float(amount),
                "percentage": float(percentage),
            }
        )

    # Process income
    for (category, currency), amount in income_data.items():
        category_node_id = get_node_id("income", category, currency.id)
        currency_node_id = get_node_id("currency", currency.name, currency.id)
        add_node(category_node_id, str(category))
        add_node(currency_node_id, currency.name)
        add_flow(category_node_id, currency_node_id, amount, currency, is_income=True)

    # Process expenses
    for (category, currency), amount in expense_data.items():
        category_node_id = get_node_id("expense", category, currency.id)
        currency_node_id = get_node_id("currency", currency.name, currency.id)
        add_node(category_node_id, str(category))
        add_node(currency_node_id, currency.name)
        add_flow(currency_node_id, category_node_id, amount, currency, is_income=False)

    # Calculate and add savings flows
    savings_data = {}  # {currency -> amount}
    for (category, currency), amount in income_data.items():
        savings_data[currency] = savings_data.get(currency, Decimal("0")) + amount
    for (category, currency), amount in expense_data.items():
        savings_data[currency] = savings_data.get(currency, Decimal("0")) - amount

    for currency, amount in savings_data.items():
        if amount > 0:
            currency_node_id = get_node_id("currency", currency.name, currency.id)
            savings_node_id = get_node_id("savings", _("Saved"), currency.id)
            add_node(savings_node_id, str(_("Saved")))
            add_flow(
                currency_node_id, savings_node_id, amount, currency, is_income=True
            )

    # Calculate total across all currencies (for reference only)
    total_amount = sum(float(amount) for amount in total_income_by_currency.values())

    return {
        "nodes": list(nodes.values()),
        "flows": flows,
        "total_amount": total_amount,
        "total_by_currency": {
            curr.name: float(amount)
            for curr, amount in total_income_by_currency.items()
        },
    }
