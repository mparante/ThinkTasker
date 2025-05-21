from django.contrib import admin
from .models import ActionablePattern, ProcessedEmail, ExtractedTask

# Register your models here.
admin.site.register(ActionablePattern)
admin.site.register(ProcessedEmail)
admin.site.register(ExtractedTask)