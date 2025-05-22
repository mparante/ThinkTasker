from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('dashboard/', views.index, name='dashboard'), 
    # path('login/nonlenovo/', views.nonlenovo_login, name='nonlenovo-login'),
    path('register/', views.register, name='register'),
    path('graph/login/', views.graph_login, name='graph-login'),
    path('graph/callback/', views.graph_callback, name='graph-callback'),
    path("profile/", views.profile, name="profile"),
    path("outlook/", views.outlook_inbox, name="outlook-inbox"),
    path("emails/sync/", views.sync_emails_view, name="sync-emails"),
    path("tasks/", views.task_list, name="task_list"),
    path("tasks/create/", views.create_task, name="create_task"),
    path("tasks/edit/<int:task_id>/", views.edit_task, name="edit_task"),
    path("tasks/delete/<int:task_id>/", views.delete_task, name="delete_task"),
    path('update-task-status/', views.update_task_status, name='update-task-status'),
]
