from django.db import models

# Create your models here.
from django.core.validators import MinValueValidator, MaxValueValidator


class Review(models.Model):
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    stars = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
