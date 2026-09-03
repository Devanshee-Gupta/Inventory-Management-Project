from django import forms
from apps.accounts.models import Profile
from django.contrib.auth.models import User
from .models import Location, StaffLocationAssignment


class LocationForm(forms.ModelForm):
    class Meta:
        model = Location
        fields = ["name", "code", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. WH01"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
        


class AssignmentForm(forms.ModelForm):
    class Meta:
        model = StaffLocationAssignment
        fields = ["staff", "location"]
        widgets = {
            "staff": forms.Select(attrs={"class": "form-select"}),
            "location": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Restricting the querysets here means Django's ModelChoiceField
        # validation itself rejects any submitted id outside these sets —
        # this is real server-side enforcement, not just UI convenience.
        self.fields["staff"].queryset = User.objects.filter(
            profile__role=Profile.Role.STAFF
        ).order_by("username")
        self.fields["location"].queryset = Location.objects.filter(
            is_active=True
        ).order_by("code")