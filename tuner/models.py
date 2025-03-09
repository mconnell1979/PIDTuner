import pandas as pd
from datetime import datetime
from django.db import models
from django.utils.timezone import now, localtime, get_current_timezone, is_naive, make_aware


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
    proportional_gain = models.FloatField(null=True, blank=True)
    integral_time = models.FloatField(null=True, blank=True)
    derivative_time = models.FloatField(null=True, blank=True)

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


class BumpTest(models.Model):
    """Model for storing bump test data associated with a trend chart."""

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

    # ✅ Lambda PID Tuning Constants
    p = models.FloatField(null=True, blank=True)
    i = models.FloatField(null=True, blank=True)
    d = models.FloatField(null=True, blank=True)
    delta_pv = models.FloatField(null=True, blank=True, help_text="Change in Process Variable (ΔPV)")
    delta_cv = models.FloatField(null=True, blank=True, help_text="Change in Process Variable (ΔPV)")
    kc = models.FloatField(null=True, blank=True)

    # ✅ Cohen-Coon PID Tuning Constants
    p_cohen = models.FloatField(null=True, blank=True)
    i_cohen = models.FloatField(null=True, blank=True)
    d_cohen = models.FloatField(null=True, blank=True)
    kc_cohen = models.FloatField(null=True, blank=True)  # ✅ Cohen-Coon Controller Gain (Kc)

    created_at = models.DateTimeField(default=now)  # ✅ Store timestamps in UTC
    updated_at = models.DateTimeField(auto_now=True)  # ✅ Auto-updates on save

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
        """Detects PV and CV columns dynamically based on naming patterns."""
        pv_keywords = ["MEAS", "Process Variable", "Input", ".PNT", ".IN"]
        cv_keywords = ["Output", ".OUT", "CV"]

        pv_col, cv_col = None, None

        for col in df.columns:
            col_upper = col.upper()
            if any(keyword in col_upper for keyword in pv_keywords) and pv_col is None:
                pv_col = col
            if any(keyword in col_upper for keyword in cv_keywords) and cv_col is None:
                cv_col = col

        # Fallback logic: Select second and last column if PV/CV detection fails
        if not pv_col and len(df.columns) > 1:
            pv_col = df.columns[1]
        if not cv_col and len(df.columns) > 2:
            cv_col = df.columns[-1]

        # Ensure exactly two columns are returned
        if pv_col and cv_col:
            return pv_col, cv_col

        raise ValueError(f"Could not determine PV or CV columns! Found: {df.columns.tolist()}")

    @staticmethod
    def parse_time_column(series):
        """Attempts to parse the time column with multiple formats before defaulting."""
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%m/%d/%Y %I:%M %p",
            "%Y/%m/%d %H:%M",
            "%d-%b-%y %H:%M:%S",
        ]
        for fmt in formats:
            try:
                return pd.to_datetime(series, format=fmt, utc=True, errors="coerce")
            except ValueError:
                continue
        return pd.to_datetime(series, utc=True, errors="coerce")  # Fallback

    @staticmethod
    def clean_timestamps(df):
        """
        Cleans and standardizes the Time column in the DataFrame.
        Ensures datetime values are in UTC.
        """
        if "Time" not in df.columns:
            raise ValueError("Missing 'Time' column in DataFrame.")

        # List of known formats to try
        known_formats = [
            "%m/%d/%Y %I:%M:%S.%f %p",  # MM/DD/YYYY hh:mm:ss.sss AM/PM
            "%m/%d/%Y %I:%M:%S %p",  # MM/DD/YYYY hh:mm:ss AM/PM (no ms)
            "%Y-%m-%d %H:%M:%S.%f",  # YYYY-MM-DD HH:MM:SS.sss
            "%Y-%m-%d %H:%M:%S",  # YYYY-MM-DD HH:MM:SS (no ms)
        ]

        def try_parsing_time(time_str):
            """Attempts parsing using predefined formats."""
            if pd.isna(time_str) or not isinstance(time_str, str):
                return None

            for fmt in known_formats:
                try:
                    return datetime.strptime(time_str, fmt)
                except ValueError:
                    continue

            return pd.NaT  # Return NaT if parsing fails

        # Apply explicit parsing instead of relying on Pandas auto-inference
        df["Time"] = df["Time"].apply(try_parsing_time)

        # Drop invalid rows (NaT)
        df.dropna(subset=["Time"], inplace=True)

        # Convert to UTC
        df["Time"] = pd.to_datetime(df["Time"], utc=True)

        return df


class LambdaVariable(models.Model):
    pid_loop = models.OneToOneField(PIDLoop, on_delete=models.CASCADE, related_name="lambda_variable")
    lambda_value = models.FloatField()
    min_lambda = models.FloatField()
    max_lambda = models.FloatField()

    def __str__(self):
        return f"Lambda for {self.pid_loop.name}: {self.lambda_value}"


class PIDCalculation(models.Model):
    """Stores PID tuning constants calculated using one or more Bump Tests."""
    pid_loop = models.ForeignKey(PIDLoop, on_delete=models.CASCADE, related_name="pid_calculations")

    # ✅ Many-to-Many: Multiple bump tests can contribute to a single tuning
    bump_tests = models.ManyToManyField(BumpTest, blank=True)

    proportional_gain = models.FloatField()
    integral_time = models.FloatField()
    derivative_time = models.FloatField()
    acceptable_filter_time = models.FloatField(default=0.5)

    # ✅ Lambda Tuning Variables (Moved from `LambdaVariable`)
    lambda_value = models.FloatField(default=10.0)
    min_lambda = models.FloatField(default=1.0)
    max_lambda = models.FloatField(default=100.0)

    # ✅ Default tuning method is Lambda
    tuning_method = models.CharField(
        max_length=50,
        choices=[("lambda", "Lambda"), ("cohen_coon", "Cohen-Coon")],
        default="lambda"
    )

    def apply_tuning(self):
        """Write tuning values to the associated bump tests (Assumed Lambda Tuning)"""
        for bump in self.bump_tests.all():
            if self.tuning_method == "lambda":
                bump.p = self.proportional_gain
                bump.i = self.integral_time
                bump.d = self.derivative_time
            elif self.tuning_method == "cohen_coon":
                bump.p_cohen = self.proportional_gain
                bump.i_cohen = self.integral_time
                bump.d_cohen = self.derivative_time
            bump.save()

    def __str__(self):
        return f"PID Calc {self.id} ({self.tuning_method})"
