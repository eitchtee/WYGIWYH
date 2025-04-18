from django.contrib import messages
from django.contrib.auth import logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
)
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.common.decorators.user import is_superuser, htmx_login_required
from apps.users.forms import (
    LoginForm,
    UserSettingsForm,
    UserUpdateForm,
    UserAddForm,
)
from apps.users.models import UserSettings
from apps.common.decorators.demo import disabled_on_demo


def logout_view(request):
    logout(request)
    return redirect(reverse("login"))


@htmx_login_required
def index(request):
    if request.user.settings.start_page == UserSettings.StartPage.MONTHLY:
        return redirect(reverse("monthly_index"))
    elif request.user.settings.start_page == UserSettings.StartPage.YEARLY_ACCOUNT:
        return redirect(reverse("yearly_index_account"))
    elif request.user.settings.start_page == UserSettings.StartPage.YEARLY_CURRENCY:
        return redirect(reverse("yearly_index_currency"))
    elif request.user.settings.start_page == UserSettings.StartPage.NETWORTH_CURRENT:
        return redirect(reverse("net_worth_current"))
    elif request.user.settings.start_page == UserSettings.StartPage.NETWORTH_PROJECTED:
        return redirect(reverse("net_worth_projected"))
    elif request.user.settings.start_page == UserSettings.StartPage.ALL_TRANSACTIONS:
        return redirect(reverse("transactions_all_index"))
    elif request.user.settings.start_page == UserSettings.StartPage.CALENDAR:
        return redirect(reverse("calendar_index"))
    else:
        return redirect(reverse("monthly_index"))


class UserLoginView(LoginView):
    form_class = LoginForm
    template_name = "users/login.html"
    redirect_authenticated_user = True


@only_htmx
@htmx_login_required
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

    response.headers["HX-Trigger"] = "updated"
    return response


@only_htmx
@htmx_login_required
def toggle_sound_playing(request):
    user_settings, created = UserSettings.objects.get_or_create(user=request.user)
    current_mute_sounds = user_settings.mute_sounds
    new_mute_sounds = not current_mute_sounds

    user_settings.mute_sounds = new_mute_sounds
    user_settings.save()

    if new_mute_sounds is True:
        messages.info(request, _("Sounds are now muted"))
        response = render(request, "users/generic/play_sounds.html")
    else:
        messages.info(request, _("Sounds will now play"))
        response = render(request, "users/generic/mute_sounds.html")

    response.headers["HX-Trigger"] = "updated"
    return response


@only_htmx
@htmx_login_required
def update_settings(request):
    user_settings = request.user.settings

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


@htmx_login_required
@is_superuser
@require_http_methods(["GET"])
def users_index(request):
    return render(
        request,
        "users/pages/index.html",
    )


@only_htmx
@htmx_login_required
@is_superuser
@require_http_methods(["GET"])
def users_list(request):
    users = get_user_model().objects.all().order_by("id")

    return render(
        request,
        "users/fragments/list.html",
        {"users": users},
    )


@only_htmx
@htmx_login_required
@is_superuser
@require_http_methods(["GET", "POST"])
def user_add(request):
    if request.method == "POST":
        form = UserAddForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Item added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = UserAddForm()

    return render(
        request,
        "users/fragments/add.html",
        {"form": form},
    )


@only_htmx
@htmx_login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def user_edit(request, pk):
    user = get_object_or_404(get_user_model(), id=pk)

    if not request.user.is_superuser and user != request.user:
        raise PermissionDenied

    if request.method == "POST":
        form = UserUpdateForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Item updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = UserUpdateForm(instance=user)

    return render(
        request,
        "users/fragments/edit.html",
        {"form": form, "user": user},
    )
