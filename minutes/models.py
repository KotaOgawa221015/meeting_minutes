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
    current_phase = models.CharField(
        max_length=20,
        choices=[
            ('introduction', '導入'),
            ('sharing', '共有'),
            ('discussion', '議論'),
            ('summary', 'まとめ'),
        ],
        default='introduction'
    )
    start_time = models.DateTimeField(null=True, blank=True)
    use_facilitator = models.BooleanField(default=False, help_text='AIファシリテーター機能を有効にする')
    use_timekeeper = models.BooleanField(default=True, help_text='タイムキーパー機能を有効にする')
    is_ended = models.BooleanField(default=False, help_text='会議が終了したかどうか')

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


class TranscriptStamp(models.Model):
    """文字起こしにスタンプを付与するモデル"""
    STAMP_CHOICES = [
        ('important', '📍 重要'),
        ('action', '✅ アクション'),
        ('decision', '📋 決定'),
        ('question', '❓ 質問'),
        ('good', '👍 良い意見'),
        ('follow_up', '🔗 フォローアップ'),
    ]
    
    transcript = models.ForeignKey(Transcript, on_delete=models.CASCADE, related_name='stamps')
    stamp_type = models.CharField(max_length=20, choices=STAMP_CHOICES)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        unique_together = ('transcript', 'stamp_type')  # 同じトランスクリプトに同じスタンプは1度だけ

    def __str__(self):
        return f"{self.get_stamp_type_display()} - {self.transcript.text[:30]}"


class TranscriptComment(models.Model):
    """文字起こしに対するコメント"""
    transcript = models.ForeignKey(Transcript, on_delete=models.CASCADE, related_name='comments')
    comment_text = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Comment on {self.transcript.text[:30]} by {self.created_by}"


class TranscriptMark(models.Model):
    """文字起こしをマーキング（ハイライト）するモデル"""
    MARK_COLORS = [
        ('yellow', '🟨 黄'),
        ('pink', '🟥 ピンク'),
        ('blue', '🟦 青'),
        ('green', '🟩 緑'),
        ('purple', '🟪 紫'),
        ('orange', '🟧 オレンジ'),
    ]
    
    transcript = models.ForeignKey(Transcript, on_delete=models.CASCADE, related_name='marks')
    color = models.CharField(max_length=20, choices=MARK_COLORS)
    note = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        unique_together = ('transcript', 'color')  # 同じトランスクリプトに同じ色は1度だけ

    def __str__(self):
        return f"{self.get_color_display()} Mark on {self.transcript.text[:30]}"