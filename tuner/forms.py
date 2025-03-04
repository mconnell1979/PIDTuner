from django import forms
from .models import TrendChart

class TrendChartUploadForm(forms.ModelForm):
    class Meta:
        model = TrendChart
        fields = ["pid_loop", "file"]
