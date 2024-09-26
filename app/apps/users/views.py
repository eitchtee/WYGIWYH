from django.contrib.auth import logout
from django.contrib.auth.views import (
    LoginView,
)
from django.shortcuts import redirect, render
from django.urls import reverse


from apps.users.forms import (
    LoginForm,
    EmailLoginForm,
)


def logout_view(request):
    logout(request)
    return redirect(reverse("inicio"))


class UserLoginView(LoginView):
    form_class = LoginForm
    # template_name = "users/login.html"
    redirect_authenticated_user = True
