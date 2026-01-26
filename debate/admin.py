from django.contrib import admin
from .models import Debate, DebateStatement


@admin.register(Debate)
class DebateAdmin(admin.ModelAdmin):
    list_display = ('title', 'ai_type', 'status', 'winner', 'created_at')
    list_filter = ('status', 'ai_type', 'winner', 'created_at')
    search_fields = ('title', 'judgment_text')
    readonly_fields = ('created_at',)


@admin.register(DebateStatement)
class DebateStatementAdmin(admin.ModelAdmin):
    list_display = ('debate', 'speaker', 'order', 'created_at')
    list_filter = ('speaker', 'created_at')
    search_fields = ('text',)
    readonly_fields = ('created_at',)

