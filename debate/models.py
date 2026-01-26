from django.db import models
from django.contrib.auth.models import User


class Debate(models.Model):
    """ディベートセッションモデル"""
    STATUS_CHOICES = [
        ('setup', 'セットアップ'),
        ('debating', 'ディベート中'),
        ('completed', '完了'),
    ]
    
    AI_TYPE_CHOICES = [
        ('logical', '論理的'),
        ('creative', '創造的'),
        ('diplomatic', '外交的'),
        ('aggressive', '攻撃的'),
    ]
    
    title = models.CharField(max_length=200)  # ディベートのテーマ
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    ai_type = models.CharField(max_length=50, choices=AI_TYPE_CHOICES, default='logical')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='setup')
    
    # 先攻後攻: 'user' = ユーザーが先攻, 'ai' = AIが先攻
    first_speaker = models.CharField(
        max_length=10,
        choices=[('user', 'ユーザー'), ('ai', 'AI')],
        default='user'
    )
    
    winner = models.CharField(
        max_length=10,
        choices=[('user', 'ユーザー'), ('ai', 'AI'), ('draw', '引き分け')],
        null=True,
        blank=True
    )
    judgment_text = models.TextField(blank=True)  # AI判定の詳細
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.created_at.strftime('%Y/%m/%d %H:%M')}"


class DebateStatement(models.Model):
    """ディベート発言記録"""
    debate = models.ForeignKey(Debate, on_delete=models.CASCADE, related_name='statements')
    speaker = models.CharField(max_length=10, choices=[('user', 'ユーザー'), ('ai', 'AI')])
    text = models.TextField()
    order = models.IntegerField()  # 発言順序
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order']
        unique_together = ('debate', 'order')
    
    def __str__(self):
        return f"{self.debate.title} - {self.speaker}の発言{self.order}"
