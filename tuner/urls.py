from django.urls import path
from .views import home, pid_loop_list, pid_loop_detail, upload_trend_chart, trend_chart_list, view_trend_chart, save_bump
from .views import delete_bump


urlpatterns = [
    path('', home, name='home'),
    path('pid-loops/', pid_loop_list, name='pid_loop_list'),
    path('pid-loop/<int:loop_id>/', pid_loop_detail, name='pid_loop_detail'),
    path("upload-trend-chart/", upload_trend_chart, name="upload_trend_chart"),
    path("trend-charts/", trend_chart_list, name="trend_chart_list"),
    path("trend-chart/<int:chart_id>/", view_trend_chart, name="view_trend_chart"),
    path("save-bump/<int:chart_id>/", save_bump, name="save_bump"),
    path("delete-bump/", delete_bump, name="delete_bump"),
]

