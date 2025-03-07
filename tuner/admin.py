from django.contrib import admin
from .models import PIDLoop, TrendChart, LambdaVariable, PIDCalculation, BumpTest

class BumpTestAdmin(admin.ModelAdmin):
    list_display = ('id', 'get_pid_loop', 'get_trend_chart_description', 'start_time', 'end_time')  # ✅ Added id
    list_filter = ('trend_chart__pid_loop',)

    def get_pid_loop(self, obj):
        return obj.trend_chart.pid_loop.name
    get_pid_loop.admin_order_field = 'trend_chart__pid_loop'
    get_pid_loop.short_description = 'PID Loop'

    def get_trend_chart_description(self, obj):
        return obj.trend_chart.description if obj.trend_chart else "No Description"
    get_trend_chart_description.admin_order_field = 'trend_chart__description'
    get_trend_chart_description.short_description = 'Trend Chart Description'


class TrendChartAdmin(admin.ModelAdmin):
    list_display = ("id", "pid_loop", "description", "uploaded_at")  # ✅ Ensured id is included
    search_fields = ("id", "pid_loop__name", "description")
    list_filter = ("uploaded_at",)


class PIDLoopAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "description", "pid_type")  # ✅ Added id column
    search_fields = ("id", "name", "description")
    list_filter = ("pid_type",)


class LambdaVariableAdmin(admin.ModelAdmin):
    list_display = ("id", "pid_loop", "lambda_value", "min_lambda", "max_lambda")  # ✅ Added id column
    search_fields = ("id", "pid_loop__name")


class PIDCalculationAdmin(admin.ModelAdmin):
    list_display = ("id", "pid_loop", "proportional_gain", "integral_time", "derivative_time", "acceptable_filter_time")  # ✅ Added id column
    search_fields = ("id", "pid_loop__name")


admin.site.register(BumpTest, BumpTestAdmin)
admin.site.register(PIDLoop, PIDLoopAdmin)
admin.site.register(TrendChart, TrendChartAdmin)
admin.site.register(LambdaVariable, LambdaVariableAdmin)
admin.site.register(PIDCalculation, PIDCalculationAdmin)
