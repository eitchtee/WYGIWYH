from django import forms


class RangeInput(forms.NumberInput):
    input_type = "range"
