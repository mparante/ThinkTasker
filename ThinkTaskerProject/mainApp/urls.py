from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('dashboard/', views.index, name='dashboard'), 
    path('login/nonlenovo/', views.nonlenovo_login, name='nonlenovo-login'),
    path('register/', views.register, name='register'),
    path('graph/login/', views.graph_login, name='graph-login'),
    path('graph/callback/', views.graph_callback, name='graph-callback'),
    path("profile/", views.profile, name="profile"),
    path("outlook/", views.outlook_inbox, name="outlook-inbox"),
]
