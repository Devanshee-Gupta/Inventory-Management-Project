from django import forms
from .models import Category, Item

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