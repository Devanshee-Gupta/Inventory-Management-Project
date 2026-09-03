from django import forms
from apps.locations.models import Location
from apps.locations.services import get_accessible_locations

from .models import Category, Item, StockMovement
from .services import calculate_item_stock_by_location

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ["sku", "name", "description", "unit_of_measure", "reorder_level", "category"]
        widgets = {
            "sku": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. ITM-0001"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "unit_of_measure": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. PCS"}),
            "reorder_level": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "category": forms.Select(attrs={"class": "form-select"}),
        }
        

class BaseMovementForm(forms.Form):
    item = forms.ModelChoiceField(
        queryset=Item.objects.filter(is_archived=False).order_by("sku"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    quantity = forms.IntegerField(min_value=1, widget=forms.NumberInput(attrs={"class": "form-control"}))

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)


class ReceiptForm(BaseMovementForm):
    location = forms.ModelChoiceField(queryset=Location.objects.none(), widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = get_accessible_locations(self.user).filter(is_active=True)


class IssueForm(BaseMovementForm):
    location = forms.ModelChoiceField(queryset=Location.objects.none(), widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["location"].queryset = get_accessible_locations(self.user).filter(is_active=True)

    def clean(self):
        cleaned = super().clean()
        item, location, qty = cleaned.get("item"), cleaned.get("location"), cleaned.get("quantity")
        if item and location and qty:
            available = calculate_item_stock_by_location(item, location)
            if available < qty:
                raise forms.ValidationError(
                    f"Insufficient stock at {location.code}: available {available}, requested {qty}."
                )
        return cleaned


class TransferForm(BaseMovementForm):
    source_location = forms.ModelChoiceField(queryset=Location.objects.none(), widget=forms.Select(attrs={"class": "form-select"}))
    destination_location = forms.ModelChoiceField(queryset=Location.objects.none(), widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accessible = get_accessible_locations(self.user).filter(is_active=True)
        self.fields["source_location"].queryset = accessible
        self.fields["destination_location"].queryset = accessible

    def clean(self):
        cleaned = super().clean()
        source, dest = cleaned.get("source_location"), cleaned.get("destination_location")
        item, qty = cleaned.get("item"), cleaned.get("quantity")
        if source and dest and source == dest:
            raise forms.ValidationError("Source and destination locations must be different.")
        if item and source and qty:
            available = calculate_item_stock_by_location(item, source)
            if available < qty:
                raise forms.ValidationError(
                    f"Insufficient stock at {source.code}: available {available}, requested {qty}. "
                    "Transfer rejected."
                )
        return cleaned


class AdjustmentForm(BaseMovementForm):
    location = forms.ModelChoiceField(queryset=Location.objects.filter(is_active=True), widget=forms.Select(attrs={"class": "form-select"}))
    adjustment_direction = forms.ChoiceField(
        choices=StockMovement.AdjustmentDirection.choices, widget=forms.Select(attrs={"class": "form-select"})
    )
    reason = forms.CharField(widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))

    def clean_reason(self):
        reason = self.cleaned_data.get("reason", "").strip()
        if not reason:
            raise forms.ValidationError("Reason is required for an adjustment.")
        return reason

    def clean(self):
        cleaned = super().clean()
        item, location = cleaned.get("item"), cleaned.get("location")
        qty, direction = cleaned.get("quantity"), cleaned.get("adjustment_direction")
        if direction == StockMovement.AdjustmentDirection.DECREASE and item and location and qty:
            available = calculate_item_stock_by_location(item, location)
            if available < qty:
                raise forms.ValidationError(
                    f"Insufficient stock at {location.code} to decrease by {qty}; available {available}."
                )
        return cleaned