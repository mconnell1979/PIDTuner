from django.db import models

from django.db import models

class PIDLoop(models.Model):
    """Model for storing information about a PID loop."""
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class TrendChart(models.Model):
    pid_loop = models.ForeignKey(PIDLoop, on_delete=models.CASCADE)  # ✅ Correct reference
    file = models.FileField(upload_to="trend_charts/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Trend Chart for {self.pid_loop.name}"


class BumpTest(models.Model):
    trend_chart = models.ForeignKey(TrendChart, on_delete=models.CASCADE, related_name="bump_tests")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    def __str__(self):
        return f"Bump Test: {self.start_time} - {self.end_time}"



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


    def __str__(self):
        return f"Bump Test ({self.start_time} - {self.end_time})"

