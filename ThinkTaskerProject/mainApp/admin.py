from django.contrib import admin
from .models import ActionablePattern, ProcessedEmail, ExtractedTask, ThinkTaskerUser

# Register your models here.
admin.site.register(ActionablePattern)
admin.site.register(ProcessedEmail)
admin.site.register(ExtractedTask)

@admin.register(ThinkTaskerUser)
class ThinkTaskerUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'department', 'is_approved', 'is_active')
    list_filter = ('is_approved', 'is_active', 'department')
    search_fields = ('email', 'username', 'first_name', 'last_name', 'department')