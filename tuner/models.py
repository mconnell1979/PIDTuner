from django.db import models
from django.utils.timezone import localtime, get_current_timezone


class PIDLoop(models.Model):
    """Model for storing information about a PID loop."""
    PID_TYPE_CHOICES = [
        ("1st Order", "1st Order"),
        ("Integrating", "Integrating"),
        ("Integrating with Lag", "Integrating with Lag"),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    pid_type = models.CharField(
        max_length=50,
        choices=PID_TYPE_CHOICES,
        default="1st Order"  # Default to "1st Order"
    )

    def save(self, *args, **kwargs):
        """Ensure all associated BumpTests update when the PIDLoop type changes."""
        super().save(*args, **kwargs)

        # ✅ Update all associated BumpTests
        for trend_chart in self.trendchart_set.all():
            for bump_test in trend_chart.bumptest_set.all():
                bump_test.save()  # ✅ Triggers update in BumpTest.save()

    def __str__(self):
        return self.name


class TrendChart(models.Model):
    pid_loop = models.ForeignKey('PIDLoop', on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    csv_file = models.FileField(upload_to='trend_charts/', blank=True, null=True)  # Add this
    description = models.TextField(blank=True, null=True)  # Ensure description is here

    def __str__(self):
        return f"Trend Chart for {self.pid_loop}"


class BumpTest(models.Model):
    id = models.AutoField(primary_key=True)
    trend_chart = models.ForeignKey("TrendChart", on_delete=models.CASCADE)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    T1 = models.DateTimeField(null=True, blank=True)
    T2 = models.DateTimeField(null=True, blank=True)
    T3 = models.DateTimeField(null=True, blank=True)
    T4 = models.DateTimeField(null=True, blank=True)

    T1_note = models.CharField(max_length=255, blank=True, null=True)
    T2_note = models.CharField(max_length=255, blank=True, null=True)
    T3_note = models.CharField(max_length=255, blank=True, null=True)
    T4_note = models.CharField(max_length=255, blank=True, null=True)

    def save(self, *args, **kwargs):
        """Ensure timestamps are stored and displayed in local time and update notes based on PIDLoop type."""
        tz = get_current_timezone()

        if self.start_time:
            self.start_time = localtime(self.start_time, tz)
        if self.end_time:
            self.end_time = localtime(self.end_time, tz)

        # ✅ Get associated PIDLoop type
        if self.trend_chart and hasattr(self.trend_chart, "pid_loop"):
            pid_type = self.trend_chart.pid_loop.pid_type

            # ✅ Update T1-T4 notes based on PIDLoop type
            if pid_type == "1st Order":
                self.T1_note = "PV Init"
                self.T2_note = "PV Moved"
                self.T3_note = "63%"
                self.T4_note = "PV Settled"
            elif pid_type == "Integrating":
                self.T1_note = "Slope 1 Start"
                self.T2_note = "Slope 1 End"
                self.T3_note = "Slope 2 Start"
                self.T4_note = "Slope 2 End"
            elif pid_type == "Integrating with Lag":
                self.T1_note = "Slope 1 Start"
                self.T2_note = "Slope Changed"
                self.T3_note = "Slope 2 Start"
                self.T4_note = "Slope 2 End"

        super().save(*args, **kwargs)

    @property
    def pid_loop_name(self):
        """Safely get the PID loop name."""
        if self.trend_chart and hasattr(self.trend_chart, "pid_loop"):
            return self.trend_chart.pid_loop.name
        return "Unknown"

    def __str__(self):
        return f"Bump Test {self.id} - {self.pid_loop_name}"


class LambdaVariable(models.Model):
    pid_loop = models.OneToOneField(PIDLoop, on_delete=models.CASCADE, related_name="lambda_variable")
    lambda_value = models.FloatField()
    min_lambda = models.FloatField()
    max_lambda = models.FloatField()

    def __str__(self):
        return f"Lambda for {self.pid_loop.name}: {self.lambda_value}"


class PIDCalculation(models.Model):
    pid_loop = models.OneToOneField(PIDLoop, on_delete=models.CASCADE, related_name="pid_calculation")
    proportional_gain = models.FloatField()
    integral_time = models.FloatField()
    derivative_time = models.FloatField()
    acceptable_filter_time = models.FloatField()

    def __str__(self):
        return f"Tuning Parameters for {self.pid_loop.name}"


