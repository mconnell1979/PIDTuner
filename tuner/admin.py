from django.contrib import admin
from .models import PIDLoop, TrendChart, PIDCalculation, BumpTest


class BumpTestAdmin(admin.ModelAdmin):
    """Admin settings for BumpTest, displaying Lambda & Cohen-Coon tuning values."""

    list_display = (
    'id', 'get_pid_loop', 'get_trend_chart_description', 'start_time', 'end_time', 'p', 'i', 'd', 'p_cohen', 'i_cohen',
    'd_cohen')
    list_filter = ('trend_chart__pid_loop',)
    readonly_fields = ('p', 'i', 'd', 'p_cohen', 'i_cohen', 'd_cohen')

    def get_pid_loop(self, obj):
        return obj.trend_chart.pid_loop.name

    get_pid_loop.admin_order_field = 'trend_chart__pid_loop'
    get_pid_loop.short_description = 'PID Loop'

    def get_trend_chart_description(self, obj):
        return obj.trend_chart.description if obj.trend_chart else "No Description"

    get_trend_chart_description.admin_order_field = 'trend_chart__description'
    get_trend_chart_description.short_description = 'Trend Chart Description'


class TrendChartAdmin(admin.ModelAdmin):
    list_display = ("id", "pid_loop", "description", "uploaded_at")
    search_fields = ("id", "pid_loop__name", "description")
    list_filter = ("uploaded_at",)


class PIDLoopAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "description", "pid_type")
    search_fields = ("id", "name", "description")
    list_filter = ("pid_type",)


class PIDCalculationAdmin(admin.ModelAdmin):
    """Admin settings for PID Calculation, showing associated Bump Tests."""
    list_display = (
    "id", "pid_loop", "tuning_method", "proportional_gain", "integral_time", "derivative_time", "get_bump_tests")
    search_fields = ("id", "pid_loop__name")
    filter_horizontal = ('bump_tests',)  # ✅ Makes bump test selection easier

    def get_bump_tests(self, obj):
        """Displays associated bump tests in list view."""
        return ", ".join([str(bump.id) for bump in obj.bump_tests.all()])

    get_bump_tests.short_description = "Bump Tests Used"


# ✅ Register Models with Admin
admin.site.register(PIDLoop, PIDLoopAdmin)
admin.site.register(TrendChart, TrendChartAdmin)
admin.site.register(PIDCalculation, PIDCalculationAdmin)
admin.site.register(BumpTest, BumpTestAdmin)
