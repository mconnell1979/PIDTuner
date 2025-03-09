from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('tuner/', include('tuner.urls', namespace='tuner')),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]

# Serving media files in development
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
