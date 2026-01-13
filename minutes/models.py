from django.db import models
from django.contrib.auth.models import User

class Meeting(models.Model):
    title = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    duration_seconds = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=[
            ('recording', '録音中'),
            ('processing', '処理中'),
            ('completed', '完了'),
        ],
        default='recording'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.created_at.strftime('%Y/%m/%d %H:%M')}"


class Transcript(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='transcripts')
    timestamp = models.FloatField()  # 会議開始からの秒数
    speaker = models.CharField(max_length=100, blank=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.meeting.title} - {self.timestamp}s"


class MinuteSummary(models.Model):
    meeting = models.OneToOneField(Meeting, on_delete=models.CASCADE, related_name='summary')
    full_transcript = models.TextField()
    summary = models.TextField()
    key_points = models.JSONField(default=list)  # ["ポイント1", "ポイント2", ...]
    action_items = models.JSONField(default=list)  # [{"task": "タスク", "assignee": "担当者"}, ...]
    decisions = models.JSONField(default=list)  # ["決定事項1", "決定事項2", ...]
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"議事録: {self.meeting.title}"