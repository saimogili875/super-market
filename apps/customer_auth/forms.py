import re
from django import forms


class ExistingCustomerLoginForm(forms.Form):
    """Form for returning customers logging in with Email only."""

    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "id": "login_email",
                "class": "form-input",
                "placeholder": "your.email@example.com",
                "required": True,
                "autocomplete": "email",
            }
        ),
        label="Email Address",
    )

    def clean_email(self):
        return self.cleaned_data.get("email", "").strip().lower()


class NewCustomerSignupForm(forms.Form):
    """Form for new customers signing up with Phone + Email."""

    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "id": "signup_phone",
                "class": "form-input",
                "placeholder": "e.g. +91 9876543210 or 9876543210",
                "required": True,
                "type": "tel",
                "autocomplete": "tel",
            }
        ),
        label="Phone Number",
    )
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "id": "signup_email",
                "class": "form-input",
                "placeholder": "your.email@example.com",
                "required": True,
                "autocomplete": "email",
            }
        ),
        label="Email Address",
    )

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()
        cleaned = re.sub(r"[\s\-\(\)]", "", phone)
        if not cleaned or len(cleaned) < 7:
            raise forms.ValidationError("Please enter a valid phone number.")
        return cleaned

    def clean_email(self):
        return self.cleaned_data.get("email", "").strip().lower()


# Backward compatibility alias
CustomerLoginForm = NewCustomerSignupForm


class OTPVerifyForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "id": "otp_code",
                "class": "form-input text-center text-xl tracking-wider",
                "placeholder": "123456",
                "required": True,
                "maxlength": "6",
                "pattern": "[0-9]{6}",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "style": "font-family: monospace; letter-spacing: 0.4em; font-size: 1.5rem; text-align: center;",
            }
        ),
        label="6-Digit Verification Code",
    )

    def clean_otp(self):
        otp = self.cleaned_data.get("otp", "").strip()
        if not otp.isdigit() or len(otp) != 6:
            raise forms.ValidationError("OTP must be a 6-digit number.")
        return otp
