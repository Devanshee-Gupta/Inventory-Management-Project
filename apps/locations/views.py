from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView
from rest_framework import viewsets

from apps.accounts.permissions import IsManager, IsManagerOrReadOnly, ManagerRequiredMixin

from .forms import AssignmentForm, LocationForm
from .models import Location, StaffLocationAssignment
from .serializers import AssignmentSerializer, LocationSerializer
from .services import filter_locations, get_accessible_locations



# ---- Location template views ----

class LocationListView(LoginRequiredMixin, ListView):
    model = Location
    template_name = "locations/location_list.html"
    context_object_name = "locations"
    paginate_by = 20
    
    def get_queryset(self):
        # Rule 7 enforced here: Manager -> all, Staff -> assigned only.
        return filter_locations(get_accessible_locations(self.request.user), self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        context["querystring"] = params.urlencode()
        return context


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


# ---- Assignment template views (Manager-only, all four operations) ----

class AssignmentListView(ManagerRequiredMixin, ListView):
    model = StaffLocationAssignment
    template_name = "locations/assignment_list.html"
    context_object_name = "assignments"
    paginate_by = 20
    queryset = StaffLocationAssignment.objects.select_related("staff", "location")


class AssignmentCreateView(ManagerRequiredMixin, CreateView):
    model = StaffLocationAssignment
    form_class = AssignmentForm
    template_name = "locations/assignment_form.html"
    success_url = reverse_lazy("assignment-list")


class AssignmentDeleteView(ManagerRequiredMixin, DeleteView):
    model = StaffLocationAssignment
    template_name = "locations/assignment_confirm_delete.html"
    success_url = reverse_lazy("assignment-list")
    # This is the one place in the system where deletion is legitimate —
    # see the branch-level note at the top of this document for why.


# ---- DRF API (session-authenticated) ----

class LocationViewSet(viewsets.ModelViewSet):
    serializer_class = LocationSerializer
    permission_classes = [IsManagerOrReadOnly]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        return filter_locations(get_accessible_locations(self.request.user), self.request.query_params)


class AssignmentViewSet(viewsets.ModelViewSet):
    """
    Manager-only in every direction, including read — assignment data is
    an administrative access-control list, not something Staff need to
    browse via the API.
    """
    queryset = StaffLocationAssignment.objects.select_related("staff", "location")
    serializer_class = AssignmentSerializer
    permission_classes = [IsManager]