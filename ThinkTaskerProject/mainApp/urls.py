from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    # Auth and profile
    path("", views.login_view, name="login"),
    path("dashboard/", views.index, name="dashboard"),
    path("register/", views.register, name="register"),
    path("graph/login/", views.graph_login, name="graph-login"),
    path("graph/callback/", views.graph_callback, name="graph-callback"),
    path("profile/", views.profile, name="profile"),

    # Outlook and sync
    path('tasks/by-date/', views.tasks_by_date, name='tasks_by_date'),
    path("emails/sync/", views.sync_emails_view, name="sync-emails"),

    # === AJAX/POST/utility endpoints for dashboard use ===
    path("update-task-status/", views.update_task_status, name="update-task-status"),
    path('tasks/recommended-deadline/', views.recommended_deadline, name='recommended_deadline'),

    # CRUD for tasks (all actions redirect back to dashboard)
    path("tasks/create/", views.create_task, name="create_task"),
    path("tasks/edit/<int:task_id>/", views.edit_task, name="edit_task"),
    path("tasks/delete/<int:task_id>/", views.delete_task, name="delete_task"),

    # Settings, Help, Logout
    path("settings/", views.settings_view, name="settings"),
    path("help-docs/", views.help_docs, name="help_docs"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
]
