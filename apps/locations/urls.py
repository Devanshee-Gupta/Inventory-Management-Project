from django.urls import path

from . import views

urlpatterns = [
    path("locations/", views.LocationListView.as_view(), name="location-list"),
    path("locations/create/", views.LocationCreateView.as_view(), name="location-create"),
    path("locations/<int:pk>/edit/", views.LocationUpdateView.as_view(), name="location-update"),
]