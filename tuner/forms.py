from django import forms
from .models import TrendChart, PIDLoop, PIDCalculation, LambdaVariable

class TrendChartUploadForm(forms.ModelForm):
    """Form to upload a TrendChart CSV file."""
    class Meta:
        model = TrendChart
        fields = ['pid_loop', 'csv_file', 'description']  # Ensure 'csv_file' is here

class PIDLoopForm(forms.ModelForm):
    """Form to create or edit a PID Loop."""
    class Meta:
        model = PIDLoop
        fields = ["name", "description", "pid_type"]

class PIDCalculationForm(forms.ModelForm):
    """Form to edit PID Tuning Parameters manually."""
    class Meta:
        model = PIDCalculation
        fields = ["proportional_gain", "integral_time", "derivative_time", "acceptable_filter_time"]

class LambdaVariableForm(forms.ModelForm):
    """Form to update Lambda tuning parameters."""
    class Meta:
        model = LambdaVariable
        fields = ["lambda_value", "min_lambda", "max_lambda"]
