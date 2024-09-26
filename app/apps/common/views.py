from django.shortcuts import render


def toasts(request):
    return render(request, "common/toasts.html")
