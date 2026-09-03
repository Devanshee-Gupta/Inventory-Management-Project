import csv
import io

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.core.exceptions import PermissionDenied, ValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError

from django.http import HttpResponse
from django.shortcuts import redirect, render

from apps.locations.models import Location

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
from .models import Category, Item, ItemHistory, StockMovement
from .serializers import CategorySerializer, ItemSerializer, ItemHistorySerializer, StockMovementSerializer
from apps.locations.services import get_accessible_locations
from .services import (
    calculate_item_stock,
    calculate_item_stock_by_location,
    get_visible_movements,
    is_below_reorder,
    record_stock_movement,
    apply_low_stock_filter,
    log_item_event,
)
from .filters import filter_categories, filter_items, filter_movements


# ---- Template views (server-rendered, Bootstrap) ----

# ---- Category template views ----
class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = "inventory/category_list.html"
    context_object_name = "categories"
    paginate_by = 20

    def get_queryset(self):
        return filter_categories(Category.objects.all(), self.request.GET)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["querystring"] = _querystring_without_page(self.request)
        return context


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
        
    def get_queryset(self):
        return filter_categories(Category.objects.all(), self.request.query_params)

        

# ---- Item template views ----

class ItemListView(LoginRequiredMixin, ListView):
    """Normal screen — Rule 5: archived items never appear here, for either role."""
    model = Item
    template_name = "inventory/item_list.html"
    context_object_name = "items"
    paginate_by = 20
    queryset = Item.objects.filter(is_archived=False).select_related("category")
    
    def get_queryset(self):
        qs = filter_items(
            Item.objects.filter(is_archived=False).select_related("category"), self.request.GET
        )
        if self.request.GET.get("low_stock") == "true":
            qs = apply_low_stock_filter(qs)  # materializes to a list — see design note
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for item in context["items"]:
            item.current_stock = calculate_item_stock(item)
            item.below_reorder = is_below_reorder(item)
        context["categories_for_filter"] = Category.objects.all()
        context["querystring"] = _querystring_without_page(self.request)
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
        context["history"] = item.history.all()  # already ordered -created_at via Meta
        return context


class ItemCreateView(ManagerRequiredMixin, CreateView):
    model = Item
    form_class = ItemForm
    template_name = "inventory/item_form.html"
    success_url = reverse_lazy("item-list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        log_item_event(
            item=self.object, event_type=ItemHistory.EventType.CREATED,
            performed_by=self.request.user, note=f"Item {self.object.sku} created.",
        )
        return response


class ItemUpdateView(ManagerRequiredMixin, UpdateView):
    model = Item
    form_class = ItemForm
    template_name = "inventory/item_form.html"
    success_url = reverse_lazy("item-list")

    def form_valid(self, form):
        # Fetch BEFORE super().form_valid() saves — see the branch-level
        # design note for why this ordering is the whole point.
        original = Item.objects.get(pk=self.object.pk)
        response = super().form_valid(form)  # form.save() happens inside here
        for field in form.changed_data:
            log_item_event(
                item=self.object, event_type=ItemHistory.EventType.UPDATED,
                performed_by=self.request.user, field_name=field,
                old_value=getattr(original, field), new_value=getattr(self.object, field),
            )
        return response

class ItemArchiveView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        item = get_object_or_404(Item, pk=pk)
        item.is_archived = True
        item.save(update_fields=["is_archived", "updated_at"]) 
        log_item_event(item=item, event_type=ItemHistory.EventType.ARCHIVED, performed_by=request.user)
        return redirect("item-list")


class ItemRestoreView(ManagerRequiredMixin, View):
    def post(self, request, pk):
        item = get_object_or_404(Item, pk=pk)
        item.is_archived = False
        item.save(update_fields=["is_archived", "updated_at"])
        log_item_event(item=item, event_type=ItemHistory.EventType.RESTORED, performed_by=request.user)
        return redirect("archived-item-list")


class ItemAddNoteView(ManagerRequiredMixin, View):
    """The NOTE event type — a freeform annotation not tied to any field change."""
    def post(self, request, pk):
        item = get_object_or_404(Item, pk=pk)
        note = (request.POST.get("note") or "").strip()
        if not note:
            messages.error(request, "Note cannot be blank.")
        else:
            log_item_event(item=item, event_type=ItemHistory.EventType.NOTE, performed_by=request.user, note=note)
            messages.success(request, "Note added.")
        return redirect("item-detail", pk=pk)

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
                qs = qs.filter(is_archived=True)
            else:
                qs = qs.filter(is_archived=False)
            qs = filter_items(qs, self.request.query_params)
            if self.request.query_params.get("low_stock") == "true":
                qs = apply_low_stock_filter(qs)
            return qs
        return qs

    def perform_create(self, serializer):
        instance = serializer.save(created_by=self.request.user)
        log_item_event(
            item=instance, event_type=ItemHistory.EventType.CREATED,
            performed_by=self.request.user, note=f"Item {instance.sku} created.",
        )
    
    def perform_update(self, serializer):
        # DRF does NOT mutate serializer.instance during is_valid() the way
        # Django's ModelForm does — .update() is what changes it, and that
        # only happens inside serializer.save() below. So the "fetch fresh
        # copy first" trick from the template side isn't needed here; the
        # pre-save instance is still genuinely the old data at this point.
        original = Item.objects.get(pk=serializer.instance.pk)
        instance = serializer.save()
        for field in serializer.validated_data.keys():
            old_value, new_value = getattr(original, field), getattr(instance, field)
            if str(old_value) != str(new_value):
                log_item_event(
                    item=instance, event_type=ItemHistory.EventType.UPDATED,
                    performed_by=self.request.user, field_name=field,
                    old_value=old_value, new_value=new_value,
                )
    
    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def archive(self, request, pk=None):
        item = self.get_object()
        item.is_archived = True
        item.save(update_fields=["is_archived", "updated_at"])
        log_item_event(item=item, event_type=ItemHistory.EventType.ARCHIVED, performed_by=request.user)
        return Response(ItemSerializer(item).data)

    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def restore(self, request, pk=None):
        item = self.get_object()
        item.is_archived = False
        item.save(update_fields=["is_archived", "updated_at"])
        log_item_event(item=item, event_type=ItemHistory.EventType.RESTORED, performed_by=request.user)
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
    
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        item = self.get_object()
        return Response(ItemHistorySerializer(item.history.all(), many=True).data)

    @action(detail=True, methods=["post"], permission_classes=[IsManager])
    def add_note(self, request, pk=None):
        item = self.get_object()
        note = (request.data.get("note") or "").strip()
        if not note:
            raise DRFValidationError({"note": "Note cannot be blank."})
        entry = log_item_event(item=item, event_type=ItemHistory.EventType.NOTE, performed_by=request.user, note=note)
        return Response(ItemHistorySerializer(entry).data, status=201)
    
    
# ---- Stock movement template views ----

class MovementListView(LoginRequiredMixin, ListView):
    """Rule 7 applies to history too: Staff only see movements touching their locations."""
    model = StockMovement
    template_name = "inventory/movement_list.html"
    context_object_name = "movements"
    paginate_by = 30

    def get_queryset(self):
        return filter_movements(get_visible_movements(self.request.user), self.request.GET)  # or .query_params for the API

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["items_for_filter"] = Item.objects.all().order_by("sku")
        context["movement_types"] = StockMovement.MovementType.choices
        context["locations_for_filter"] = get_accessible_locations(self.request.user)
        context["querystring"] = _querystring_without_page(self.request)
        return context

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
        return filter_movements(get_visible_movements(self.request.user), self.request.GET)  # or .query_params for the API
        

def _querystring_without_page(request):
    """Shared helper: preserves active filters when a pagination link is clicked."""
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()



# ---- Export ----

class ItemExportView(LoginRequiredMixin, View):
    """Respects the exact same filters as /items/ — export what you're looking at."""

    def get(self, request):
        items = filter_items(
            Item.objects.filter(is_archived=False).select_related("category"), request.GET
        )
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="items.csv"'
        writer = csv.writer(response)
        writer.writerow(["sku", "name", "description", "unit_of_measure", "reorder_level", "category", "current_stock"])
        for item in items:
            writer.writerow([
                item.sku, item.name, item.description, item.unit_of_measure,
                item.reorder_level, item.category.name, calculate_item_stock(item),
            ])
        return response


class MovementExportView(LoginRequiredMixin, View):
    """Respects Rule 7 (via get_visible_movements) and the same filters as /movements/."""

    def get(self, request):
        movements = filter_movements(get_visible_movements(request.user), request.GET)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="stock_movements.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "created_at", "movement_type", "sku", "quantity", "location",
            "source_location", "destination_location", "adjustment_direction", "reason", "recorded_by",
        ])
        for m in movements:
            writer.writerow([
                m.created_at.isoformat(), m.movement_type, m.item.sku, m.quantity,
                m.location.code if m.location else "",
                m.source_location.code if m.source_location else "",
                m.destination_location.code if m.destination_location else "",
                m.adjustment_direction or "", m.reason, m.recorded_by.username,
            ])
        return response


# ---- Import ----

class ItemImportView(ManagerRequiredMixin, View):
    template_name = "inventory/item_import.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        upload = request.FILES.get("csv_file")
        if not upload:
            messages.error(request, "Please choose a CSV file.")
            return redirect("item-import")

        try:
            decoded = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            messages.error(request, "Could not read the file — please upload a UTF-8 encoded CSV.")
            return redirect("item-import")

        reader = csv.DictReader(io.StringIO(decoded))
        required = {"sku", "name", "unit_of_measure", "reorder_level", "category"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            messages.error(request, f"CSV must include columns: {', '.join(sorted(required))}")
            return redirect("item-import")

        created, skipped, errors = 0, 0, []
        for row_num, row in enumerate(reader, start=2):  # row 1 is the header
            sku = (row.get("sku") or "").strip().upper()
            name = (row.get("name") or "").strip()
            category_name = (row.get("category") or "").strip()
            try:
                if not sku or not name or not category_name:
                    raise ValueError("sku, name, and category are required.")
                if Item.objects.filter(sku=sku).exists():
                    skipped += 1
                    continue
                category = Category.objects.get(name__iexact=category_name)
                reorder_level = int(row.get("reorder_level") or 0)
                if reorder_level < 0:
                    raise ValueError("reorder_level cannot be negative.")
                Item.objects.create(
                    sku=sku, name=name,
                    description=(row.get("description") or "").strip(),
                    unit_of_measure=(row.get("unit_of_measure") or "").strip(),
                    reorder_level=reorder_level, category=category, created_by=request.user,
                )
                created += 1
            except Category.DoesNotExist:
                errors.append(f"Row {row_num}: category '{category_name}' does not exist.")
            except (ValueError, TypeError) as exc:
                errors.append(f"Row {row_num}: {exc}")

        messages.success(request, f"Import finished: {created} created, {skipped} skipped (duplicate SKU), {len(errors)} errors.")
        for err in errors[:20]:
            messages.warning(request, err)
        return redirect("item-list")


class MovementImportView(LoginRequiredMixin, View):
    """
    Manager AND Staff can access this screen — exactly like the manual
    Receipt/Issue/Transfer forms. Adjustment rows from a Staff upload are
    rejected per-row by record_stock_movement() itself, the same guard
    used everywhere else; there is no separate check needed here.
    """
    template_name = "inventory/movement_import.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        upload = request.FILES.get("csv_file")
        if not upload:
            messages.error(request, "Please choose a CSV file.")
            return redirect("movement-import")

        try:
            decoded = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            messages.error(request, "Could not read the file — please upload a UTF-8 encoded CSV.")
            return redirect("movement-import")

        reader = csv.DictReader(io.StringIO(decoded))
        required = {"sku", "movement_type", "quantity"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            messages.error(request, f"CSV must include columns: {', '.join(sorted(required))}")
            return redirect("movement-import")

        def get_location(code):
            code = (code or "").strip().upper()
            return Location.objects.get(code=code) if code else None

        created, errors = 0, []
        for row_num, row in enumerate(reader, start=2):
            sku = (row.get("sku") or "").strip().upper()
            try:
                item = Item.objects.get(sku=sku)
                movement_type = (row.get("movement_type") or "").strip().upper()
                quantity = int(row.get("quantity") or 0)
                record_stock_movement(
                    item=item,
                    movement_type=movement_type,
                    quantity=quantity,
                    recorded_by=request.user,
                    location=get_location(row.get("location")),
                    source_location=get_location(row.get("source_location")),
                    destination_location=get_location(row.get("destination_location")),
                    reason=(row.get("reason") or "").strip(),
                    adjustment_direction=(row.get("adjustment_direction") or "").strip().upper() or None,
                )
                created += 1
            except Item.DoesNotExist:
                errors.append(f"Row {row_num}: item SKU '{sku}' not found.")
            except Location.DoesNotExist:
                errors.append(f"Row {row_num}: a location code in this row does not exist.")
            except (ValidationError, PermissionDenied) as exc:
                errors.append(f"Row {row_num}: {exc}")
            except (ValueError, TypeError):
                errors.append(f"Row {row_num}: quantity must be a whole number.")

        messages.success(request, f"Import finished: {created} movements recorded, {len(errors)} errors.")
        for err in errors[:20]:
            messages.warning(request, err)
        return redirect("movement-list")