from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from django.db.models import Q
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, FormView, ListView, UpdateView
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import (
    IsManager,
    IsManagerOrReadOnly,
    ManagerRequiredMixin,
    is_manager,
)

from .forms import CategoryForm, ItemForm, AdjustmentForm, IssueForm, ReceiptForm, TransferForm
from .models import Category, Item, StockMovement
from .serializers import CategorySerializer, ItemSerializer, StockMovementSerializer
from apps.locations.services import get_accessible_locations
from .services import (
    calculate_item_stock,
    calculate_item_stock_by_location,
    is_below_reorder,
    record_stock_movement,
)


# ---- Template views (server-rendered, Bootstrap) ----

# ---- Category template views ----
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
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Computed per-item for the current page only (max `paginate_by` items,
        # so this is a bounded number of extra queries, not N+1 over the whole table).
        for item in context["items"]:
            item.current_stock = calculate_item_stock(item)
            item.below_reorder = is_below_reorder(item)
        return context

class ArchivedItemListView(ManagerRequiredMixin, ListView):
    """Manager-only screen — the one place archived items are browsable, for restoring."""
    model = Item
    template_name = "inventory/archived_item_list.html"
    context_object_name = "items"
    paginate_by = 20
    queryset = Item.objects.filter(is_archived=True).select_related("category")
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for item in context["items"]:
            item.current_stock = calculate_item_stock(item)
        return context


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
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        item = self.object
        context["current_stock"] = calculate_item_stock(item)
        context["is_below_reorder"] = is_below_reorder(item)
        # Rule 7 applies here too: Staff only see the breakdown for locations
        # they're assigned to; Managers see every location.
        accessible = get_accessible_locations(self.request.user)
        context["location_breakdown"] = [
            {"location": loc, "stock": calculate_item_stock_by_location(item, loc)}
            for loc in accessible
        ]
        return context


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
    
    @action(detail=True, methods=["get"])
    def stock(self, request, pk=None):
        item = self.get_object()
        accessible = get_accessible_locations(request.user)
        breakdown = [
            {
                "location_id": loc.pk,
                "location_code": loc.code,
                "quantity": calculate_item_stock_by_location(item, loc),
            }
            for loc in accessible
        ]
        return Response({
            "item": item.sku,
            "current_stock": calculate_item_stock(item),
            "reorder_level": item.reorder_level,
            "is_below_reorder": is_below_reorder(item),
            "by_location": breakdown,
        })
    

# ---- Stock movement template views ----

class MovementListView(LoginRequiredMixin, ListView):
    """Rule 7 applies to history too: Staff only see movements touching their locations."""
    model = StockMovement
    template_name = "inventory/movement_list.html"
    context_object_name = "movements"
    paginate_by = 30

    def get_queryset(self):
        qs = StockMovement.objects.select_related(
            "item", "location", "source_location", "destination_location", "recorded_by"
        )
        if is_manager(self.request.user):
            return qs
        accessible_ids = set(get_accessible_locations(self.request.user).values_list("pk", flat=True))
        return qs.filter(
            Q(location_id__in=accessible_ids)
            | Q(source_location_id__in=accessible_ids)
            | Q(destination_location_id__in=accessible_ids)
        )


class BaseMovementCreateView(LoginRequiredMixin, FormView):
    template_name = "inventory/movement_form.html"
    success_url = reverse_lazy("movement-list")
    movement_type = None
    page_title = None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = self.page_title
        return ctx

    def build_movement_kwargs(self, form):
        return {
            "item": form.cleaned_data["item"],
            "quantity": form.cleaned_data["quantity"],
        }

    def form_valid(self, form):
        try:
            record_stock_movement(
                movement_type=self.movement_type,
                recorded_by=self.request.user,
                **self.build_movement_kwargs(form),
            )
        except (ValidationError, PermissionDenied) as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, f"{self.page_title} recorded.")
        return super().form_valid(form)


class ReceiptCreateView(BaseMovementCreateView):
    form_class = ReceiptForm
    movement_type = StockMovement.MovementType.RECEIPT
    page_title = "Receipt"

    def build_movement_kwargs(self, form):
        kwargs = super().build_movement_kwargs(form)
        kwargs["location"] = form.cleaned_data["location"]
        return kwargs


class IssueCreateView(BaseMovementCreateView):
    form_class = IssueForm
    movement_type = StockMovement.MovementType.ISSUE
    page_title = "Issue"

    def build_movement_kwargs(self, form):
        kwargs = super().build_movement_kwargs(form)
        kwargs["location"] = form.cleaned_data["location"]
        return kwargs


class TransferCreateView(BaseMovementCreateView):
    form_class = TransferForm
    movement_type = StockMovement.MovementType.TRANSFER
    page_title = "Transfer"

    def build_movement_kwargs(self, form):
        kwargs = super().build_movement_kwargs(form)
        kwargs["source_location"] = form.cleaned_data["source_location"]
        kwargs["destination_location"] = form.cleaned_data["destination_location"]
        return kwargs


class AdjustmentCreateView(ManagerRequiredMixin, BaseMovementCreateView):
    form_class = AdjustmentForm
    movement_type = StockMovement.MovementType.ADJUSTMENT
    page_title = "Adjustment"

    def build_movement_kwargs(self, form):
        kwargs = super().build_movement_kwargs(form)
        kwargs["location"] = form.cleaned_data["location"]
        kwargs["adjustment_direction"] = form.cleaned_data["adjustment_direction"]
        kwargs["reason"] = form.cleaned_data["reason"]
        return kwargs


# ---- DRF API (session-authenticated) ----

class StockMovementViewSet(viewsets.ModelViewSet):
    """
    A single endpoint handling all four movement types via `movement_type`
    in the payload — mirrors the template side exactly, both calling
    record_stock_movement() as the only path that creates a row.

    No PUT/PATCH/DELETE at all (Rule 2) — enforced here at the HTTP-method
    level, on top of the model.save()/delete() guards as a second layer.
    """
    serializer_class = StockMovementSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        qs = StockMovement.objects.select_related(
            "item", "location", "source_location", "destination_location", "recorded_by"
        )
        if is_manager(self.request.user):
            return qs
        accessible_ids = set(get_accessible_locations(self.request.user).values_list("pk", flat=True))
        return qs.filter(
            Q(location_id__in=accessible_ids)
            | Q(source_location_id__in=accessible_ids)
            | Q(destination_location_id__in=accessible_ids)
        )
        

