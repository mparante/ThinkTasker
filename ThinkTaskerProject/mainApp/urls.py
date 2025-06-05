from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    # Auth and profile
    path("login/", views.login_view, name="login"),
    path("dashboard/", views.index, name="dashboard"),
    path("register/", views.register, name="register"),
    path("graph/login/", views.graph_login, name="graph-login"),
    path("graph/callback/", views.graph_callback, name="graph-callback"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),

    # Outlook and sync
    path('tasks/by-date/', views.tasks_by_date, name='tasks_by_date'),
    path("emails/sync/", views.sync_emails_view, name="sync-emails"),
    path("tasks/all/", views.all_tasks_json, name="all_tasks_json"),

    # AJAX/POST/utility endpoints for dashboard use
    path("update-task-status/", views.update_task_status, name="update-task-status"),
    path("tasks/create/", views.create_task, name="create_task"),
    path("tasks/edit/<int:task_id>/", views.edit_task, name="edit_task"),
    path("tasks/delete/<int:task_id>/", views.delete_task, name="delete_task"),
    path("tasks/delete-completed/", views.delete_completed_tasks, name="delete_completed_tasks"),

]
