from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('',      include('mainApp.urls')),  # catches dashboard, login, etc.
    path('admin/', admin.site.urls),
]