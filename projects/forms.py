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
        label="Number of Simulations ",
        validators=[
            MinValueValidator(
                1, message="The number of simulations must be at least 1."
            ),
            MaxValueValidator(
                1000000,
                message="The number of simulations cannot exceed 1,000,000.  This limit ensures server resources aren't overused.",
            ),
        ],
    )
    min_val = forms.FloatField(label="Minimum Value")
    max_val = forms.FloatField(label="Maximum Value")
    target_val = forms.FloatField(label="Target Value")

    second_sim_quantity = forms.IntegerField(
        required=False,
        label="Second Number of Simulations",
        validators=[
            MinValueValidator(
                1,
                message="The value for second number of simulations, if you wish to include a second data range, must be at least 1.  If you only want one data range in your graph, please leave the secondary fields blank.",
            ),
            MaxValueValidator(
                1000000,
                message="The number of second simulations cannot exceed 1,000,000.  This limit ensures server resources aren't overused.",
            ),
        ],
    )
    second_min_val = forms.FloatField(label="Second Minimum Value", required=False)
    second_max_val = forms.FloatField(label="Second Maximum Value", required=False)
    second_target_val = forms.FloatField(label="Second Target Value", required=False)
