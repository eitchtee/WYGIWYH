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
)
from apps.common.decorators.htmx import only_htmx


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
    current_hide_amounts = request.user.settings.hide_amounts
    new_hide_amounts = not current_hide_amounts

    request.user.settings.hide_amounts = new_hide_amounts
    request.user.settings.save()

    if new_hide_amounts is True:
        messages.info(request, _("Transaction amounts are now hidden"))
        response = HttpResponse(
            '<i class="fa-solid fa-eye-slash fa-fw"></i><div id="settings-hide-amounts" class="d-inline tw-invisible"></div>'
        )
    else:
        messages.info(request, _("Transaction amounts are now displayed"))
        response = HttpResponse('<i class="fa-solid fa-eye fa-fw"></i>')

    response.headers["HX-Trigger"] = "transaction_updated, toast"
    return response
