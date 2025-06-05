# This script is for the modals used at add and edit tasks at dashboard.

from django import forms
from .models import ExtractedTask

class ExtractedTaskForm(forms.ModelForm):
    deadline = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date'}),
        input_formats=['%Y-%m-%d']
    )

    class Meta:
        model = ExtractedTask
        fields = [
            "subject",            # The title of the task
            "task_description",   # Task details/description
            "priority",           # Urgent, Important, Medium, Low
            "status",             # Open, Ongoing, Completed, etc.
            "deadline",           # Deadline (date/time)
        ]
        widgets = {
            'priority': forms.Select(choices=[
                ('Urgent', 'Urgent'),
                ('Important', 'Important'),
                ('Medium', 'Medium'),
                ('Low', 'Low'),
            ]),
            'status': forms.Select(choices=[
                ('Open', 'Open'),
                ('Ongoing', 'Ongoing'),
            ]),
        }
