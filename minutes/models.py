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
    include_ai_in_summary = models.BooleanField(default=True, help_text='要約にAIの発言を含めるかどうか')

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
        indexes = [
            models.Index(fields=['meeting', 'timestamp']),
        ]

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
        indexes = [
            models.Index(fields=['transcript']),
        ]

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
        indexes = [
            models.Index(fields=['transcript']),
        ]

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
        indexes = [
            models.Index(fields=['transcript']),
        ]

    def __str__(self):
        return f"{self.get_color_display()} Mark on {self.transcript.text[:30]}"


class AIMember(models.Model):
    """AI参加者モデル"""
    PERSONALITY_CHOICES = [
        ('idea', '💡 新たなアイディアを提案'),
        ('facilitator', '🎯 議論を促進'),
        ('cheerful', '😊 明るい'),
        ('negative', '😟 ネガティブ'),
        ('angry', '😠 怒りっぽい'),
    ]
    
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='ai_members')
    name = models.CharField(max_length=100, default='AI')
    personality = models.CharField(
        max_length=20,
        choices=PERSONALITY_CHOICES,
        default='facilitator'
    )
    is_active = models.BooleanField(default=True)
    voicevox_speaker_id = models.IntegerField(default=1)  # VoiceVoxのスピーカーID
    voicevox_style_id = models.IntegerField(default=0)  # VoiceVoxのスタイルID
    voicevox_speed = models.FloatField(default=1.0)  # 再生速度 (0.5-2.0)
    voicevox_pitch = models.FloatField(default=0.0)  # ピッチ (-0.15-0.15)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['meeting', 'is_active']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.name or self.name == 'AI':
            # デフォルト名を生成: personality + 連番
            # より効率的に取得（COUNTの方がより最適化される）
            from django.db.models import Count
            existing_count = (
                AIMember.objects
                .filter(meeting=self.meeting, personality=self.personality)
                .aggregate(count=Count('id'))['count']
            )
            self.name = f"{self.personality}{existing_count + 1}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} ({self.get_personality_display()}) - {self.meeting.title}"


class AIMemberResponse(models.Model):
    """AIメンバーの返答記録"""
    ai_member = models.ForeignKey(AIMember, on_delete=models.CASCADE, related_name='responses')
    triggered_by = models.ForeignKey(Transcript, on_delete=models.SET_NULL, null=True, blank=True, related_name='triggered_ai_responses')
    # AIレスポンスがトリガーソースの場合（AI同士の議論）
    triggered_by_ai_response = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='triggered_ai_responses_chain')
    response_text = models.TextField()
    timestamp = models.FloatField()  # 会議開始からの秒数
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['ai_member', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.ai_member.name}: {self.response_text[:50]}..."