"""Admin-dashboard forms for account management.

Reuses Django's UserCreationForm so passwords are ALWAYS hashed (set_password)
and validated by the configured password validators — the dashboard never
stores or displays a raw password. The AgentProfile is provisioned by the
calling service/view, mirroring the Sprint 1 Django-admin creation logic.
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import Role, User


class AgentCreationForm(UserCreationForm):
    """Create a delivery-agent account (role forced to AGENT).

    Inherits password1/password2 (hashed on save) from UserCreationForm and
    adds the optional phone. The view calls AgentProfile.objects.get_or_create
    after save() so every agent has an availability profile.
    """

    phone = forms.CharField(max_length=20, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Apply the design-system input class to every field widget.
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-input")

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.role = Role.AGENT
        user.phone = self.cleaned_data.get("phone", "")
        if commit:
            user.save()
        return user
