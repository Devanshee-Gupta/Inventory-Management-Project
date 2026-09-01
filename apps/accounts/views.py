from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import render

from .forms import StyledAuthenticationForm


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = StyledAuthenticationForm
    redirect_authenticated_user = True


class CustomLogoutView(LogoutView):
    next_page = "login"


@login_required
def home_view(request):
    """
    Temporary placeholder landing page after login.
    Replaced by the real dashboard in feature/dashboard (STEP 11).
    """
    return render(request, "accounts/home.html")