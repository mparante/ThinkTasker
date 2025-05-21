from django.contrib import admin
from .models import ActionablePattern, ProcessedEmail, ExtractedTask

# Register your models here.
# Register the ActionablePattern model with the Django admin site.
admin.site.register(ActionablePattern)
admin.site.register(ProcessedEmail)
admin.site.register(ExtractedTask)