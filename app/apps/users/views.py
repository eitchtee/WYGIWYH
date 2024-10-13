from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
)
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.users.forms import (
    LoginForm,
    UserSettingsForm,
)
from apps.common.decorators.htmx import only_htmx
from apps.users.models import UserSettings


def logout_view(request):
    logout(request)
    return redirect(reverse("login"))


class UserLoginView(LoginView):
    form_class = LoginForm
    template_name = "users/login.html"
    redirect_authenticated_user = True


@only_htmx
@login_required
def toggle_amount_visibility(request):
    user_settings, created = UserSettings.objects.get_or_create(user=request.user)
    current_hide_amounts = user_settings.hide_amounts
    new_hide_amounts = not current_hide_amounts

    user_settings.hide_amounts = new_hide_amounts
    user_settings.save()

    if new_hide_amounts is True:
        messages.info(request, _("Transaction amounts are now hidden"))
        response = render(request, "users/generic/show_amounts.html")
    else:
        messages.info(request, _("Transaction amounts are now displayed"))
        response = render(request, "users/generic/hide_amounts.html")

    response.headers["HX-Trigger"] = "updated, toast"
    return response


@only_htmx
@login_required
def update_settings(request):
    user_settings, created = UserSettings.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = UserSettingsForm(request.POST, instance=user_settings)
        if form.is_valid():
            form.save()
            messages.success(request, _("Your settings have been updated"))
            return HttpResponse(
                status=204,
                headers={"HX-Refresh": "true"},
            )
    else:
        form = UserSettingsForm(instance=user_settings)

    return render(request, "users/fragments/user_settings.html", {"form": form})
