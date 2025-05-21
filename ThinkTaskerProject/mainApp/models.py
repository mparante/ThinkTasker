from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

# This model is used to store user information.
# It extends the AbstractUser model to include an is_approved field.
# The is_approved field is used to indicate if the user has been approved for access to the system.
# The model is used to manage user accounts and their approval status in the database.
class ThinkTaskerUser(AbstractUser):
    is_approved = models.BooleanField(default=False)
    department = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.email or self.username

# This is the model used to store actionable patterns.
# It includes the pattern itself, the type of pattern (word, phrase, regex), a label for the pattern,
# a priority level, and a boolean to indicate if the pattern is active.
# The model is used to identify and categorize tasks based on the patterns found in the text.
class ActionablePattern(models.Model):
    PATTERN_TYPE_CHOICES = [
        ('word', 'Word'),
        ('phrase', 'Phrase'),
        ('regex', 'Regular Expression'),
    ]

    pattern = models.CharField(max_length=128)
    pattern_type = models.CharField(max_length=16, choices=PATTERN_TYPE_CHOICES, default='word')

    label = models.CharField(max_length=64, blank=True)
    # Tasks are categorized as Urgent, Important, Medium, or Low based on relevance and deadlines
    priority = models.CharField(max_length=32, blank=True) 
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.pattern} ({self.pattern_type})"

# This model is used to store the processed emails.
# Each processed email is associated with a message ID, a subject, and a timestamp of when it was processed.
# It also includes a boolean to indicate if the email is actionable, a foreign key to the extracted task,
# and a boolean to indicate if the email is new.
# The model is used to track the status of processed emails and their associated tasks.
# The is_actionable field is used to indicate if the email contains actionable content.
# The processed_at field is used to store the timestamp of when the email was processed.
# The task field is used to link the processed email to the extracted task.
# The is_new field is used to indicate if the email is new and has not been processed before.
# The model is used to manage processed emails and their associated tasks in the database.
class ProcessedEmail(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="processed_emails")    
    message_id = models.CharField(max_length=256, unique=True)
    subject = models.CharField(max_length=512)
    body_preview = models.TextField(blank=True, null=True)
    processed_at = models.DateTimeField(auto_now_add=True)
    is_actionable = models.BooleanField(default=False)
    is_new = models.BooleanField(default=True)
    web_link = models.URLField(max_length=1024, blank=True, null=True)

    def __str__(self):
        return f"{self.subject} - Actionable: {self.is_actionable}"
    
# This model is used to store the extracted tasks from emails.
# Each task is associated with an email ID, a subject, a body preview, and a list of actionable patterns.
# It also includes a priority level, a deadline, and a status to indicate if the task is open or completed.
# The model is used to track the progress of tasks and their associated emails.
# The status field is used to indicate if the task is open, in progress, or completed.
# The created_at field is used to store the timestamp of when the task was created.
# The model is used to manage tasks and their associated emails in the database.
class ExtractedTask(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tasks")
    email = models.ForeignKey(ProcessedEmail, on_delete=models.CASCADE, related_name='tasks')
    task_description = models.TextField()
    actionable_patterns = models.JSONField(default=list, blank=True)
    priority = models.CharField(max_length=16, blank=True)
    deadline = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=32, default="Open")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        email_subject = self.email.subject if self.email else "No Subject"
        return f"{email_subject} ({self.status})"