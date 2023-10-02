from django import forms
from .models import Review
from django.forms import ModelForm


class ReviewForm(forms.Form):
    qr_text = forms.CharField(
        label="",
        max_length=8000,
        widget=forms.TextInput(attrs={"class": "myform", "size": 80}),
    )
