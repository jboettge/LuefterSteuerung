from django import forms

class SpecialModeForm(forms.Form):
    special_mode = forms.BooleanField(required=False)