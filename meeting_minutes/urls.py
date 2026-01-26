from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('minutes.urls')),        # 議事録アプリのURL
    path('debate/', include('debate.urls')),   # ディベートアプリのURL
]