from django import forms
from .models import Review
from django.forms import ModelForm


class ReviewForm(forms.Form):
    qr_text = forms.CharField(
        label="",
        max_length=8000,
        widget=forms.TextInput(attrs={"class": "myform", "size": 80}),
    )


from django import forms
from django.core.validators import MinValueValidator, MaxValueValidator


class MonteCarloForm(forms.Form):
    sim_quantity = forms.IntegerField(
        label="Number of Simulations: ",
        validators=[
            MinValueValidator(1, message="Value must be at least 1."),
            MaxValueValidator(
                1000000,
                message="The number of simulations cannot exceed 1,000,000.  This limit ensures server resources aren't overused.",
            ),
        ],
    )
    min_val = forms.FloatField(label="Minimum Value: ")
    max_val = forms.FloatField(label="Maximum Value: ")
    target_val = forms.FloatField(label="Target Value: ")
