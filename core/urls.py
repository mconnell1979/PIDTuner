from django.urls import path
from . import views

app_name = 'core'  # ✅ This registers the namespace 'core'

urlpatterns = [
    path('', views.home, name='home'),  # Homepage
    path('about/', views.about, name='about'),  # About page
]