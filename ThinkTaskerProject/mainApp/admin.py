from django.contrib import admin
from .models import ActionablePattern, ProcessedEmail, ExtractedTask, ThinkTaskerUser, ReferenceDocument

# Register your models here.
admin.site.register(ActionablePattern)
admin.site.register(ProcessedEmail)

@admin.register(ThinkTaskerUser)
class ThinkTaskerUserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'department', 'is_approved', 'is_active', 'last_synced_datetime')
    list_filter = ('is_approved', 'is_active', 'department')
    search_fields = ('email', 'username', 'first_name', 'last_name', 'department')

@admin.register(ReferenceDocument)
class ReferenceDocumentAdmin(admin.ModelAdmin):
    list_display = ("subject", "created_at")
    search_fields = ("subject", "body")

@admin.register(ExtractedTask)
class ExtractedTaskAdmin(admin.ModelAdmin):
    list_display = ('email', 'subject', 'priority', 'deadline', 'status', 'created_at')
    list_filter = ('priority', 'status', 'created_at')
    search_fields = ('email__subject', 'subject', 'body_preview')
    raw_id_fields = ('email',)
    ordering = ('-created_at',)