from django.urls import path

from . import views

urlpatterns = [
    path("alerts/", views.AlertListView.as_view(), name="alert-list"),
    path("alerts/<int:pk>/dismiss/", views.AlertDismissView.as_view(), name="alert-dismiss"),
]