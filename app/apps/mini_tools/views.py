from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def unit_price_calculator(request):
    return render(request, "mini_tools/unit_price_calculator.html")
