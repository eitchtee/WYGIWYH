from django.db.models import Sum
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


def generate_sankey_data(transactions_queryset):
    """
    Generates Sankey diagram data from transaction queryset.
    Uses a 1-5 scale for flows based on percentages.
    """
    nodes: Dict[str, SankeyNode] = {}
    flows: List[SankeyFlow] = []

    # Aggregate transactions
    income_data = {}  # {(category, currency, account) -> amount}
    expense_data = {}  # {(category, currency, account) -> amount}
    total_amount = Decimal("0")

    for transaction in transactions_queryset:
        currency = transaction.account.currency
        account = transaction.account
        category = transaction.category or _("Uncategorized")

        key = (category, currency, account)

        if transaction.type == "IN":
            income_data[key] = income_data.get(key, Decimal("0")) + transaction.amount
        else:
            expense_data[key] = expense_data.get(key, Decimal("0")) + transaction.amount

        total_amount += transaction.amount

    # Function to add flow
    def add_flow(from_node, to_node, amount, currency):
        percentage = (amount / total_amount) * 100 if total_amount else 0
        scaled_flow = 1 + min(percentage / 5, 2)  # Scale 1-5, capping at 100%
        flows.append(
            {
                "from_node": from_node,
                "to_node": to_node,
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
        nodes[from_node] = {"name": from_node}
        nodes[to_node] = {"name": to_node}

    # Process income
    for (category, currency, account), amount in income_data.items():
        category_name = f"{category} ({currency.code})"
        account_name = f"{account.name} ({currency.code})"
        add_flow(category_name, account_name, amount, currency)

    # Process expenses
    for (category, currency, account), amount in expense_data.items():
        category_name = f"{category} ({currency.code})"
        account_name = f"{account.name} ({currency.code})"
        add_flow(account_name, category_name, amount, currency)

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
            account_name = f"{account.name} ({currency.code})"
            savings_name = f"{_('Savings')} ({currency.code})"
            add_flow(account_name, savings_name, amount, currency)

    return {
        "nodes": list(nodes.values()),
        "flows": flows,
        "total_amount": float(total_amount),
    }
