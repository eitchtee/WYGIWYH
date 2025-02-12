from django.shortcuts import render

from apps.transactions.models import Transaction
from apps.insights.utils.sankey import generate_sankey_data


def index(request):
    return render(request, "insights/pages/index.html")


def sankey(request):
    # Get filtered transactions
    transactions = Transaction.objects.filter(date__year=2025)

    # Generate Sankey data
    sankey_data = generate_sankey_data(transactions)
    print(sankey_data)

    return render(
        request, "insights/fragments/sankey.html", {"sankey_data": sankey_data}
    )
