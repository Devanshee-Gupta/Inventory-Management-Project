from django.urls import path

from . import views

urlpatterns = [
    path("categories/", views.CategoryListView.as_view(), name="category-list"),
    path("categories/create/", views.CategoryCreateView.as_view(), name="category-create"),
    path("categories/<int:pk>/edit/", views.CategoryUpdateView.as_view(), name="category-update"),
    
    path("items/", views.ItemListView.as_view(), name="item-list"),
    path("items/archived/", views.ArchivedItemListView.as_view(), name="archived-item-list"),
    path("items/create/", views.ItemCreateView.as_view(), name="item-create"),
    path("items/<int:pk>/", views.ItemDetailView.as_view(), name="item-detail"),
    path("items/<int:pk>/edit/", views.ItemUpdateView.as_view(), name="item-update"),
    path("items/<int:pk>/archive/", views.ItemArchiveView.as_view(), name="item-archive"),
    path("items/<int:pk>/restore/", views.ItemRestoreView.as_view(), name="item-restore"),
    
    path("movements/", views.MovementListView.as_view(), name="movement-list"),
    path("movements/receipt/", views.ReceiptCreateView.as_view(), name="movement-receipt"),
    path("movements/issue/", views.IssueCreateView.as_view(), name="movement-issue"),
    path("movements/transfer/", views.TransferCreateView.as_view(), name="movement-transfer"),
    path("movements/adjustment/", views.AdjustmentCreateView.as_view(), name="movement-adjustment"),

]