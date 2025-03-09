from django import forms
from .models import TrendChart, PIDLoop  # ✅ Import PIDLoop model

class TrendChartUploadForm(forms.ModelForm):
    class Meta:
        model = TrendChart
        fields = ['pid_loop', 'csv_file', 'description']  # Ensure 'csv_file' is here

class PIDLoopForm(forms.ModelForm):  # ✅ New form for creating PID Loops
    class Meta:
        model = PIDLoop
        fields = ["name", "description", "pid_type"]
