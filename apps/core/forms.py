from django import forms


class ContactForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "class": "form-input",
                "placeholder": "Your Name",
                "required": True,
            }
        ),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-input",
                "placeholder": "your.email@example.com",
                "required": True,
            }
        ),
    )
    message = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-textarea",
                "placeholder": "Write your message here...",
                "rows": 5,
                "required": True,
            }
        ),
    )
