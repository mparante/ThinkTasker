from django.db import models

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