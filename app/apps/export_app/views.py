from django.shortcuts import render

from apps.export_app.resources.transactions import TransactionResource


# Create your views here.
def export(request):
    dataset = TransactionResource().export()
    print(dataset.csv)
