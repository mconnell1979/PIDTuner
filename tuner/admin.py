from django.contrib import admin
from .models import PIDLoop, TrendChart, LambdaVariable, PIDCalculation, BumpTest

class BumpTestAdmin(admin.ModelAdmin):
    list_display = ('get_pid_loop', 'start_time', 'end_time')
    list_filter = ('trend_chart__pid_loop',)

    def get_pid_loop(self, obj):
        return obj.trend_chart.pid_loop.name
    get_pid_loop.admin_order_field = 'trend_chart__pid_loop'  # Allows sorting
    get_pid_loop.short_description = 'PID Loop'  # Column name in admin

admin.site.register(BumpTest, BumpTestAdmin)
admin.site.register(PIDLoop)
admin.site.register(TrendChart)
admin.site.register(LambdaVariable)
admin.site.register(PIDCalculation)


