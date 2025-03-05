from django import forms
from .models import TrendChart

class TrendChartUploadForm(forms.ModelForm):
    class Meta:
        model = TrendChart
        fields = ['pid_loop', 'csv_file', 'description']  # Ensure 'csv_file' is here

