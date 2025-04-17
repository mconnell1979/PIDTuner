from django.urls import path
from .views import upload_trend_chart, trend_chart_list, view_trend_chart, save_bump
from .views import delete_bump, identity_trend, identity_trend_detail, update_t1_t2
from .views import pid_calculation_list, pid_calculation_detail, recalculate_pid
from .views import PIDLoopCreateView

from .views import (
    pid_loop_list, pid_loop_detail, pid_loop_create)
from .views import pid_calculation_detail, update_bump_tests

app_name = 'tuner'  # This is the namespace
urlpatterns = [
    path('pid-loops/', pid_loop_list, name='pid_loop_list'),
    path('pid-loop/<int:loop_id>/', pid_loop_detail, name='pid_loop_detail'),
    path('pid-loop/new/', pid_loop_create, name='pid_loop_create'),
    path("pid-calculation/<int:loop_id>/", pid_calculation_detail, name="pid_calculation_detail"),
    path('pid-loop/new/', PIDLoopCreateView.as_view(), name='pid_loop_create'),
    path("upload-trend-chart/", upload_trend_chart, name="upload_trend_chart"),
    path("trend-charts/", trend_chart_list, name="trend_chart_list"),
    path("trend-chart/<int:chart_id>/", view_trend_chart, name="view_trend_chart"),
    path("save-bump/<int:chart_id>/", save_bump, name="save_bump"),
    path("update-bump-tests/<int:pid_calculation_id>/", update_bump_tests, name="update_bump_tests"),
    path("delete-bump/", delete_bump, name="delete_bump"),
    path('identity-trend/', identity_trend, name='identity_trend_list'),
    path('identity-trend/<int:chart_id>/<int:bump_test_id>/', identity_trend_detail, name='identity_trend_detail'),
    path("update_t1_t2/<int:bump_test_id>/", update_t1_t2, name="update_t1_t2"),
    path("pid-calculations/", pid_calculation_list, name="pid_calculation_list"),
    path("recalculate-pid/<int:loop_id>/", recalculate_pid, name="recalculate_pid"),
]


