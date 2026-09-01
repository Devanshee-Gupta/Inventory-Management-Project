from django.urls import path

from . import views

urlpatterns = [
    path("categories/", views.CategoryListView.as_view(), name="category-list"),
    path("categories/create/", views.CategoryCreateView.as_view(), name="category-create"),
    path("categories/<int:pk>/edit/", views.CategoryUpdateView.as_view(), name="category-update"),
]