from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch

from .models import ThinkTaskerUser, ExtractedTask

class ThinkTaskerTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = ThinkTaskerUser.objects.create_user(
            username="testuser",
            email="testuser@outlook.com",
            password="testpass123",
            is_active=True,
            is_approved=True
        )

    def test_login_view(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_register_view_get(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_register_view_post(self):
        response = self.client.post(reverse("register"), {
            "email": "newuser@outlook.com",
            "first_name": "New",
            "last_name": "User",
            "department": "Engineering"
        })
        self.assertEqual(response.status_code, 302)  # Should redirect to login
        self.assertTrue(ThinkTaskerUser.objects.filter(email="newuser@outlook.com").exists())

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_dashboard_view(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)

    @patch("mainApp.views._get_graph_token", return_value="fake-token")
    @patch("mainApp.todo.create_todo_task", return_value=("fake-task-id", "fake-list-id"))
    def test_create_task_view(self, mock_todo, mock_token):
        self.client.force_login(self.user)
        
        response = self.client.post(reverse("create_task"), {
            "subject": "Test Task",
            "task_description": "This is a test task description.",
            "priority": "Important",
            "deadline": (timezone.now().date() + timedelta(days=3)).isoformat(),
            "status": "Open",  # Include status if your form requires it
            "view": "kanban"
        })

        # Debugging in case of failure
        if ExtractedTask.objects.count() == 0:
            print("Create task failed. Response status:", response.status_code)
            print("Redirected to:", response.url)
            print("ExtractedTask count:", ExtractedTask.objects.count())

        self.assertEqual(response.status_code, 302)  # Should redirect
        self.assertEqual(ExtractedTask.objects.count(), 1)

        task = ExtractedTask.objects.first()
        self.assertEqual(task.subject, "Test Task")
        self.assertEqual(task.priority, "Important")
        self.assertEqual(task.status, "Open")

    def test_all_tasks_json_authenticated(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("all_tasks_json"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("tasks", response.json())

    def test_update_task_status_invalid_request(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("update-task-status"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["success"])

    def test_delete_completed_tasks(self):
        self.client.force_login(self.user)
        ExtractedTask.objects.create(
            user=self.user,
            subject="Completed task",
            task_description="Done",
            status="Completed"
        )
        response = self.client.post(reverse("delete_completed_tasks"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ExtractedTask.objects.filter(user=self.user).count(), 0)

    def test_index_calendar_data(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("dashboard") + "?year=2025&month=6")
        self.assertEqual(response.status_code, 200)
        self.assertIn("calendar_weeks", response.context)

    def test_index_with_query(self):
        self.client.force_login(self.user)
        ExtractedTask.objects.create(
            user=self.user,
            subject="Query Test",
            task_description="testing",
            priority="Low",
            deadline=timezone.now().date()
        )
        response = self.client.get(reverse("dashboard") + "?q=Query")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Query Test", response.content.decode())
