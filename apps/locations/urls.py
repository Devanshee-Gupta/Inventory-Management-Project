from django.urls import path

from . import views

urlpatterns = [
    path("locations/", views.LocationListView.as_view(), name="location-list"),
    path("locations/create/", views.LocationCreateView.as_view(), name="location-create"),
    path("locations/<int:pk>/edit/", views.LocationUpdateView.as_view(), name="location-update"),
    
    path("assignments/", views.AssignmentListView.as_view(), name="assignment-list"),
    path("assignments/create/", views.AssignmentCreateView.as_view(), name="assignment-create"),
    path("assignments/<int:pk>/delete/", views.AssignmentDeleteView.as_view(), name="assignment-delete"),
]