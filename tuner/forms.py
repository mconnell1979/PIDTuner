from django import forms
from .models import TrendChart, PIDLoop, PIDCalculation, LambdaVariable


class TrendChartUploadForm(forms.ModelForm):
    """Form to upload a TrendChart CSV file with PID Loop selection."""

    pid_loop = forms.ModelChoiceField(
        queryset=PIDLoop.objects.all(),
        empty_label="Select a PID Loop",
        widget=forms.Select(attrs={"class": "form-control"})  # ✅ Bootstrap styling
    )

    csv_file = forms.FileField(
        widget=forms.FileInput(attrs={"class": "form-control"})
    )

    description = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter description..."})
    )

    class Meta:
        model = TrendChart
        fields = ["pid_loop", "csv_file", "description"]


class PIDLoopForm(forms.ModelForm):
    """Form to create or edit a PID Loop."""

    name = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Loop Name"})
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Description"})
    )
    pid_type = forms.ChoiceField(
        choices=PIDLoop.PID_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": "form-control"})
    )

    class Meta:
        model = PIDLoop
        fields = ["name", "description", "pid_type"]


class PIDCalculationForm(forms.ModelForm):
    """Form to edit PID Tuning Parameters manually."""

    proportional_gain = forms.FloatField(
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    integral_time = forms.FloatField(
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    derivative_time = forms.FloatField(
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    acceptable_filter_time = forms.FloatField(
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )

    class Meta:
        model = PIDCalculation
        fields = ["proportional_gain", "integral_time", "derivative_time", "acceptable_filter_time"]


class LambdaVariableForm(forms.ModelForm):
    """Form to update Lambda tuning parameters."""

    lambda_value = forms.FloatField(
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    min_lambda = forms.FloatField(
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )
    max_lambda = forms.FloatField(
        widget=forms.NumberInput(attrs={"class": "form-control"})
    )

    class Meta:
        model = LambdaVariable
        fields = ["lambda_value", "min_lambda", "max_lambda"]
