from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView
from rest_framework import viewsets

from apps.accounts.permissions import IsManagerOrReadOnly, ManagerRequiredMixin

from .forms import LocationForm
from .models import Location
from .serializers import LocationSerializer


# ---- Template views ----

class LocationListView(LoginRequiredMixin, ListView):
    model = Location
    template_name = "locations/location_list.html"
    context_object_name = "locations"
    paginate_by = 20

    def get_queryset(self):
        # Every authenticated user sees every location in this branch.
        # Staff-only-assigned-locations filtering is added in feature/staff-assignment.
        return Location.objects.all()


class LocationCreateView(ManagerRequiredMixin, CreateView):
    model = Location
    form_class = LocationForm
    template_name = "locations/location_form.html"
    success_url = reverse_lazy("location-list")


class LocationUpdateView(ManagerRequiredMixin, UpdateView):
    model = Location
    form_class = LocationForm
    template_name = "locations/location_form.html"
    success_url = reverse_lazy("location-list")


# ---- DRF API (session-authenticated) ----

class LocationViewSet(viewsets.ModelViewSet):
    """
    list/retrieve  -> any authenticated user
    create/update  -> Manager only
    delete         -> disabled (use is_active=False instead, see model docstring)
    """
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [IsManagerOrReadOnly]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]