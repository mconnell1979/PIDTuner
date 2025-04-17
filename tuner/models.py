import pandas as pd
from datetime import datetime
from django.db import models
from django.utils.timezone import now, localtime, get_current_timezone, is_naive, make_aware
from django.db.models.signals import post_save
from django.dispatch import receiver


class PIDLoop(models.Model):
    """Model for storing information about a PID loop."""
    PID_TYPE_CHOICES = [
        ("1st Order", "1st Order"),
        ("Integrating", "Integrating"),
        ("Integrating with Lag", "Integrating with Lag"),
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    pid_type = models.CharField(max_length=50, choices=PID_TYPE_CHOICES, default="1st Order")

    # ✅ Process Variable & Output Limits
    pv_max = models.FloatField(default=100.0)
    pv_min = models.FloatField(default=0.0)
    out_max = models.FloatField(default=100.0)
    out_min = models.FloatField(default=0.0)

    # ✅ Official Selected PID Tuning (Manually Entered or Copied from PIDCalculation)
    proportional_gain = models.FloatField(default=0.5, null=True, blank=True)
    integral_time = models.FloatField(default=10.0, null=True, blank=True)
    derivative_time = models.FloatField(default=0.0, null=True, blank=True)

    # ✅ The selected PIDCalculation (if any) that was chosen as the final tuning
    selected_pid_calculation = models.ForeignKey(
        'PIDCalculation', on_delete=models.SET_NULL, null=True, blank=True, related_name="official_pid_loop"
    )

    def set_official_tuning(self, pid_calculation):
        """Sets the official PID tuning based on a selected PIDCalculation."""
        self.selected_pid_calculation = pid_calculation
        self.proportional_gain = pid_calculation.proportional_gain
        self.integral_time = pid_calculation.integral_time
        self.derivative_time = pid_calculation.derivative_time
        self.save()

    def __str__(self):
        return self.name


@receiver(post_save, sender=PIDLoop)
def create_pid_calculation(sender, instance, created, **kwargs):
    if created and not PIDCalculation.objects.filter(pid_loop=instance).exists():
        PIDCalculation.objects.create(pid_loop=instance)
        print(f"✅ Created default PIDCalculation for PIDLoop {instance.id}")


class BumpTest(models.Model):
    """Model for storing bump test data associated with a trend chart."""
    DOMINANCE_CHOICES = [
        ("General", "General"),
        ("Lag Time Dominant", "Lag Time Dominant"),
        ("Dead Time Dominant", "Dead Time Dominant"),
    ]

    id = models.AutoField(primary_key=True)
    trend_chart = models.ForeignKey("TrendChart", on_delete=models.CASCADE)

    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    T1 = models.DateTimeField(null=True, blank=True)
    T2 = models.DateTimeField(null=True, blank=True)
    T3 = models.DateTimeField(null=True, blank=True)
    T4 = models.DateTimeField(null=True, blank=True)
    TCV = models.DateTimeField(null=True, blank=True, help_text="CV Changed")

    T1_note = models.CharField(max_length=255, blank=True, null=True)
    T2_note = models.CharField(max_length=255, blank=True, null=True)
    T3_note = models.CharField(max_length=255, blank=True, null=True)
    T4_note = models.CharField(max_length=255, blank=True, null=True)

    # ✅ Lambda PID Tuning Constants
    p = models.FloatField(default=0.5,null=True, blank=True)
    i = models.FloatField(default=10.0, null=True, blank=True)
    d = models.FloatField(default=0.0,null=True, blank=True)
    delta_pv = models.FloatField(default=0.0,null=True, blank=True, help_text="Change in Process Variable (ΔPV)")
    delta_cv = models.FloatField(default=0.0,null=True, blank=True, help_text="Change in Process Variable (ΔPV)")
    kc = models.FloatField(default=0.0,null=True, blank=True)
    Td = models.FloatField(default=0.0,null=True, blank=True, help_text="Deadtime in seconds")
    tau = models.FloatField(default=10.0,null=True, blank=True, help_text="Time Constant in seconds")

    # New Fields: Lambda Limits
    max_lambda = models.FloatField(default=100.0, help_text="Maximum Lambda value for tuning.")
    min_lambda = models.FloatField(default=1.0, help_text="Minimum Lambda value for tuning.")

    # ✅ Cohen-Coon PID Tuning Constants
    p_cohen = models.FloatField(default=0.0,null=True, blank=True)
    i_cohen = models.FloatField(default=10.0,null=True, blank=True)
    d_cohen = models.FloatField(default=0.0,null=True, blank=True)
    kc_cohen = models.FloatField(default=0.0,null=True, blank=True)  # ✅ Cohen-Coon Controller Gain (Kc)

    # New Field: Dominance Type
    dominance = models.CharField(
        max_length=50,
        choices=DOMINANCE_CHOICES,
        default="General",
        help_text="Defines whether the bump test is General, Lag Time Dominant, or Dead Time Dominant."
    )

    created_at = models.DateTimeField(default=now)  # ✅ Store timestamps in UTC
    updated_at = models.DateTimeField(auto_now=True)  # ✅ Auto-updates on save

    def update_t_notes(self):
        """Updates the T-note fields based on PID Loop Type."""
        pid_loop = self.trend_chart.pid_loop  # Get associated PIDLoop

        if pid_loop.pid_type == "1st Order":
            self.T1_note = "Initial Start"
            self.T2_note = "PV Changed"
            self.T3_note = "PV 63%"
            self.T4_note = "PV Settled"
        elif pid_loop.pid_type == "Integrating":
            self.T1_note = "Slope 1 Start"
            self.T2_note = "Slope 1 Changed"
            self.T3_note = "Slope 2 Start"
            self.T4_note = "Slope 2 End"
        elif pid_loop.pid_type == "Integrating with Lag":
            self.T1_note = "Slope 1 Start"
            self.T2_note = "Slope 1 Changed"
            self.T3_note = "Slope 2 Start"
            self.T4_note = "Slope 2 End"
        else:
            self.T1_note = None
            self.T2_note = None
            self.T3_note = None
            self.T4_note = None

    def update_dominance_and_lambda(self):
        """Automatically calculates dominance, min_lambda, and max_lambda."""
        if self.Td is None or self.tau is None or self.tau <= 0:
            return  # Avoid invalid calculations

        # ✅ Handle case where Td = 0
        if self.Td == 0:
            self.dominance = "General"
            self.min_lambda = 0.8 * self.tau
            self.max_lambda = 4 * self.tau
            print(
                f"📌 Td is 0, setting dominance to General. Min Lambda: {self.min_lambda}, Max Lambda: {self.max_lambda}")
            return

        # ✅ Normal dominance calculation
        ratio = self.tau / self.Td
        if ratio <= 2:
            self.dominance = "Dead Time Dominant"
        elif ratio >= 4:
            self.dominance = "Lag Time Dominant"
        else:
            self.dominance = "General"

        # ✅ Calculate min_lambda and max_lambda
        if self.dominance == "General":
            self.min_lambda = max(2 * self.Td, 0.8 * self.tau)
        elif self.dominance == "Dead Time Dominant":
            self.min_lambda = 2 * self.Td
            self.max_lambda = 4 * self.tau
        elif self.dominance == "Lag Time Dominant":
            self.min_lambda = 0.8 * self.tau
            self.max_lambda = 4 * self.tau

        print(f"📌 Updated Dominance: {self.dominance}, Min Lambda: {self.min_lambda}, Max Lambda: {self.max_lambda}")

    def save(self, *args, **kwargs):
        """Ensure T-notes, dominance, and lambda values are updated before saving."""
        self.update_t_notes()  # ✅ Update T-notes based on PID Type
        self.update_dominance_and_lambda()  # ✅ Update dominance and lambda values
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Bump Test {self.id} - {self.trend_chart.pid_loop.name}"


class TrendChart(models.Model):
    """Model to store uploaded trend chart files."""

    pid_loop = models.ForeignKey("PIDLoop", on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(default=now)  # Stored in UTC
    csv_file = models.FileField(upload_to="trend_charts/", blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    def save(self, *args, **kwargs):
        """Ensure uploaded_at is stored in UTC but only convert if naive."""
        if self.uploaded_at and is_naive(self.uploaded_at):
            self.uploaded_at = make_aware(self.uploaded_at)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Trend Chart for {self.pid_loop}"

    @staticmethod
    def detect_pv_cv_columns(df):
        """
        Detects PV and CV columns dynamically.
        Prioritizes known keywords but falls back to assuming 2nd & last columns.
        """
        pv_keywords = ["MEAS", "Process Variable", "Input", ".PNT", ".IN", "PV"]
        cv_keywords = ["Output", ".OUT", "CV"]

        pv_col = next((col for col in df.columns if any(k in col.upper() for k in pv_keywords)), None)
        cv_col = next((col for col in df.columns if any(k in col.upper() for k in cv_keywords)), None)

        # Fallback to 2nd and last column if needed
        if not pv_col and len(df.columns) > 1:
            pv_col = df.columns[1]
        if not cv_col and len(df.columns) > 2:
            cv_col = df.columns[-1]

        if not pv_col or not cv_col:
            raise ValueError(f"Could not determine PV or CV columns! Found: {df.columns.tolist()}")

        return pv_col, cv_col

    @staticmethod
    def parse_time_column(series):
        """Parses a time column using multiple date formats, defaults to `dateutil` if needed."""
        formats = [
            "%m/%d/%Y %I:%M:%S.%f %p",  # 3/3/2025 2:23:13.004 PM
            "%m/%d/%Y %I:%M:%S %p",  # 3/3/2025 2:23:33 PM
            "%m/%d/%Y %H:%M:%S.%f",  # 2/27/2025 17:08:57.000
            "%m/%d/%Y %H:%M:%S",  # 2/27/2025 17:08:57
            "%m/%d/%Y %I:%M %p",  # 2/27/2025 5:08 PM
            "%m/%d/%Y %H:%M",  # 2/27/2025 17:08
        ]

        for fmt in formats:
            try:
                return pd.to_datetime(series, format=fmt, errors="coerce")
            except ValueError:
                continue

        return pd.to_datetime(series, errors="coerce")  # Fallback to flexible parsing


class LambdaVariable(models.Model):
    pid_loop = models.OneToOneField(PIDLoop, on_delete=models.CASCADE, related_name="lambda_variable")
    lambda_value = models.FloatField()
    min_lambda = models.FloatField()
    max_lambda = models.FloatField()

    def __str__(self):
        return f"Lambda for {self.pid_loop.name}: {self.lambda_value}"


class PIDCalculation(models.Model):
    pid_loop = models.ForeignKey(PIDLoop, on_delete=models.CASCADE, related_name="pid_calculations")
    bump_tests = models.ManyToManyField(BumpTest, blank=True)  # ✅ Keeps a manual link but filters now
    proportional_gain = models.FloatField(default=0.0)
    integral_time = models.FloatField(default=1.0)
    derivative_time = models.FloatField(default=0.0)
    acceptable_filter_time = models.FloatField(default=0.5)
    lambda_value = models.FloatField(default=10.0)
    min_lambda = models.FloatField(default=1.0)
    max_lambda = models.FloatField(default=100.0)
    tuning_method = models.CharField(
        max_length=50,
        choices=[("lambda", "Lambda"), ("cohen_coon", "Cohen-Coon")],
        default="lambda"
    )

    def recalculate_lambda_tuning(self):
        """Perform lambda tuning calculations based on loop type."""
        # ✅ Only include bumps from this specific PIDLoop
        bumps = self.bump_tests.filter(trend_chart__pid_loop=self.pid_loop)

        if self.pid_loop.pid_type == "1st Order":
            for bump in bumps:
                if bump.T2 and bump.T3 and bump.TCV and bump.delta_cv:
                    bump.Td = (bump.T2 - bump.TCV).total_seconds()
                    bump.tau = (bump.T3 - bump.T2).total_seconds()
                    bump.kc = (
                            (bump.delta_pv / (self.pid_loop.pv_max - self.pid_loop.pv_min)) /
                            (bump.delta_cv / (self.pid_loop.out_max - self.pid_loop.out_min))
                    )

                    bump.p = round(bump.tau / (bump.kc * (self.lambda_value + bump.Td)), 3)
                    bump.i = round(bump.tau, 1)
                    bump.d = round((bump.Td * bump.tau) / (bump.Td + self.lambda_value), 2)

                    bump.save()

        elif self.pid_loop.pid_type in ["Integrating", "Integrating with Lag"]:
            for bump in bumps:
                if bump.T1 and bump.T2 and bump.T3 and bump.T4 and bump.TCV and bump.delta_cv:
                    bump.kc = (bump.T4 - bump.T3).total_seconds() / (
                            (bump.T2 - bump.T1).total_seconds() * bump.delta_cv
                    )
                    bump.Td = (bump.T2 - bump.TCV).total_seconds()
                    bump.i = round(2 * self.lambda_value + bump.Td, 1)
                    bump.p = round(bump.i / (abs(bump.kc) * (self.lambda_value + bump.Td) ** 2), 3)
                    bump.d = 0  # No need to round, it's always 0

                    bump.save()

        # ✅ Aggregate tuning values across only **filtered** bumps
        selected_bumps = [b for b in bumps if b.p is not None]

        if selected_bumps:
            self.proportional_gain = round(sum(b.p for b in selected_bumps) / len(selected_bumps), 3)
            self.integral_time = round(sum(b.i for b in selected_bumps) / len(selected_bumps), 1)
            self.derivative_time = round(sum(b.d for b in selected_bumps) / len(selected_bumps), 2)

            # ✅ Calculate min_lambda and max_lambda with rounding
            self.min_lambda = round(max(b.min_lambda for b in selected_bumps), 1)
            self.max_lambda = round(min(b.max_lambda for b in selected_bumps), 1)

        else:
            self.proportional_gain = 0.0
            self.integral_time = 1.0
            self.derivative_time = 0.0
            self.min_lambda = 1.0  # Default value
            self.max_lambda = 100.0  # Default value

        self.save()

    def recalculate_tuning(self):
        """Recalculates the PID tuning based on the selected method."""
        if self.tuning_method == "lambda":
            self.recalculate_lambda_tuning()
        self.save()

    def __str__(self):
        return f"PID Calc {self.id} ({self.tuning_method})"