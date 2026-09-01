from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import (
    IsManager,
    IsManagerOrReadOnly,
    ManagerRequiredMixin,
    is_manager,
)

from .forms import CategoryForm, ItemForm
from .models import Category, Item
from .serializers import CategorySerializer, ItemSerializer


# ---- Template views (server-rendered, Bootstrap) ----

class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = "inventory/category_list.html"
    context_object_name = "categories"
    paginate_by = 20


class CategoryCreateView(ManagerRequiredMixin, CreateView):
    model = Category
    form_class = CategoryForm
    template_name = "inventory/category_form.html"
    success_url = reverse_lazy("category-list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class CategoryUpdateView(ManagerRequiredMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = "inventory/category_form.html"
    success_url = reverse_lazy("category-list")
    # NOTE: created_by is not in CategoryForm.fields, so it cannot be
    # overwritten through this view even if the form is tampered with.


# ---- DRF API (session-authenticated) ----

class CategoryViewSet(viewsets.ModelViewSet):
    """
    list/retrieve  -> any authenticated user (Manager or Staff)
    create/update  -> Manager only
    delete         -> disabled entirely (no business rule permits deleting
                       a Category once items may reference it)
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsManagerOrReadOnly]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
        

# ---- Item template views ----

class ItemListView(LoginRequiredMixin, ListView):
    """Normal screen — Rule 5: archived items never appear here, for either role."""
    model = Item
    template_name = "inventory/item_list.html"
    context_object_name = "items"
    paginate_by = 20
    queryset = Item.objects.filter(is_archived=False).select_related("category")


class ArchivedItemListView(ManagerRequiredMixin, ListView):
    """Manager-only screen — the one place archived items are browsable, for restoring."""
    model = Item
    template_name = "inventory/archived_item_list.html"
    context_object_name = "items"
    paginate_by = 20
    queryset = Item.objects.filter(is_archived=True).select_related("category")


class ItemDetailView(LoginRequiredMixin, DetailView):
    """
    Not filtered by is_archived — a direct link to an archived item's detail
    page still works, since Rule 5 only requires movement history (and by
    extension the item record itself) to remain visible, not vanish outright.
    Only the *list* screens hide archived items.
    """
    model = Item
    template_name = "inventory/item_detail.html"
    context_object_name = "item"


class ItemCreateView(ManagerRequiredMixin, CreateView):
    model = Item
    form_class = ItemForm
    template_name = "inventory/item_form.html"
    success_url = reverse_lazy("item-list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class ItemUpdateView(ManagerRequiredMixin, UpdateView):
    model = Item
    form_class = ItemForm
    template_name = "inventory/item_form.html"
    success_url = reverse_lazy("item-list")


class ItemArchiveView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        item = get_object_or_404(Item, pk=pk)
        item.is_archived = True
        item.save(update_fields=["is_archived", "updated_at"])
        return redirect("item-list")


class ItemRestoreView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        item = get_object_or_404(Item, pk=pk)
        item.is_archived = False
        item.save(update_fields=["is_archived", "updated_at"])
        return redirect("archived-item-list")


# ---- DRF API (session-authenticated) ----

class ItemViewSet(viewsets.ModelViewSet):
    """
    list    -> excludes archived by default; Managers may pass ?archived=true
               to see the archived set instead.
    retrieve/update -> not filtered by archived status (mirrors ItemDetailView).
    create/update   -> Manager only.
    delete          -> disabled entirely; archive/restore are the only
                       supported lifecycle transitions (Rule 5).
    archive/restore -> dedicated actions, Manager only, so this is the one
                       and only code path that flips is_archived — ready to
                       have ItemHistory logging attached in STEP 12.
    """
    serializer_class = ItemSerializer
    permission_classes = [IsManagerOrReadOnly]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        qs = Item.objects.select_related("category", "created_by")
        if self.action == "list":
            if self.request.query_params.get("archived") == "true" and is_manager(self.request.user):
                return qs.filter(is_archived=True)
            return qs.filter(is_archived=False)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def archive(self, request, pk=None):
        item = self.get_object()
        item.is_archived = True
        item.save(update_fields=["is_archived", "updated_at"])
        return Response(ItemSerializer(item).data)

    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def restore(self, request, pk=None):
        item = self.get_object()
        item.is_archived = False
        item.save(update_fields=["is_archived", "updated_at"])
        return Response(ItemSerializer(item).data)