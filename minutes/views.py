from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import json
from .models import Meeting, MinuteSummary, Transcript, TranscriptStamp, TranscriptComment, TranscriptMark

def index(request):
    """会議一覧"""
    meetings = Meeting.objects.all()
    return render(request, 'minutes/index.html', {'meetings': meetings})


def create_meeting(request):
    """新しい会議を作成"""
    if request.method == 'POST':
        title = request.POST.get('title', '無題の会議')
        
        meeting = Meeting.objects.create(
            title=title,
            created_by=request.user if request.user.is_authenticated else None,
            status='recording',
            duration_seconds=0,  # roomで設定
            use_facilitator=False  # roomで有効化
        )
        return redirect('meeting_room', meeting_id=meeting.id)
    return render(request, 'minutes/create.html')


def meeting_room(request, meeting_id):
    """会議ルーム（録音画面）"""
    meeting = get_object_or_404(Meeting, id=meeting_id)
    return render(request, 'minutes/room.html', {'meeting': meeting})


def meeting_detail(request, meeting_id):
    """議事録詳細"""
    meeting = get_object_or_404(Meeting, id=meeting_id)
    try:
        summary = meeting.summary
    except MinuteSummary.DoesNotExist:
        summary = None
    
    return render(request, 'minutes/detail.html', {
        'meeting': meeting,
        'summary': summary,
        'transcripts': meeting.transcripts.all()
    })


def delete_meeting(request, meeting_id):
    """会議削除"""
    if request.method == 'DELETE':
        meeting = get_object_or_404(Meeting, id=meeting_id)
        meeting.delete()
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=405)


def end_meeting(request, meeting_id):
    """会議終了"""
    if request.method == 'POST':
        meeting = get_object_or_404(Meeting, id=meeting_id)
        meeting.is_ended = True
        meeting.status = 'completed'  # 会議終了時のみstatusを変更
        meeting.save()
        return JsonResponse({'status': 'success', 'is_ended': meeting.is_ended})
    return JsonResponse({'status': 'error'}, status=405)


def get_meeting_status(request, meeting_id):
    """会議のステータスを取得"""
    meeting = get_object_or_404(Meeting, id=meeting_id)
    return JsonResponse({
        'is_ended': meeting.is_ended,
        'status': meeting.status,
        'duration_seconds': meeting.duration_seconds
    })


@require_http_methods(["POST"])
def save_manual_transcript(request, meeting_id):
    """手動入力されたトランスクリプトをサーバーに保存"""
    try:
        meeting = get_object_or_404(Meeting, id=meeting_id)
        data = json.loads(request.body)
        text = data.get('text', '').strip()
        
        if not text:
            return JsonResponse({'status': 'error', 'message': 'text is required'}, status=400)
        
        # タイムスタンプを計算（会議開始時からの秒数）
        if meeting.start_time:
            from django.utils import timezone
            elapsed = (timezone.now() - meeting.start_time).total_seconds()
        else:
            elapsed = 0
        
        # トランスクリプトを作成
        transcript = Transcript.objects.create(
            meeting=meeting,
            timestamp=elapsed,
            speaker='手動入力',
            text=text
        )
        
        return JsonResponse({
            'status': 'success',
            'transcript_id': transcript.id,
            'text': transcript.text,
            'timestamp': transcript.timestamp
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def get_meeting_data(request, meeting_id):
    """会議のトランスクリプトと要約データを取得"""
    meeting = get_object_or_404(Meeting, id=meeting_id)
    
    # トランスクリプトデータを取得
    transcripts = meeting.transcripts.all().order_by('timestamp')
    transcript_list = [
        {
            'id': t.id,
            'timestamp': t.timestamp,
            'speaker': t.speaker,
            'text': t.text
        }
        for t in transcripts
    ]
    
    # 要約データを取得
    summary_data = None
    try:
        summary = meeting.summary
        # action_itemsは辞書のリストなので、JSONエンコード可能にする
        action_items = summary.action_items if isinstance(summary.action_items, list) else []
        key_points = summary.key_points if isinstance(summary.key_points, list) else []
        decisions = summary.decisions if isinstance(summary.decisions, list) else []
        
        summary_data = {
            'summary': summary.summary,
            'key_points': key_points,
            'action_items': action_items,
            'decisions': decisions
        }
        print(f"[DEBUG] Summary loaded for meeting {meeting_id}: {summary_data}")
    except MinuteSummary.DoesNotExist:
        print(f"[DEBUG] No summary found for meeting {meeting_id}")
    except Exception as e:
        print(f"[DEBUG] Error loading summary: {e}")
    
    response_data = {
        'transcripts': transcript_list,
        'summary': summary_data,
        'transcript_count': len(transcript_list)
    }
    print(f"[DEBUG] API Response for meeting {meeting_id}: {response_data}")
    
    return JsonResponse(response_data, safe=False)


def readme(request):
    """READMEページ"""
    return render(request, 'minutes/readme.html')


# ========================================
# Transcript Stamp API (スタンプ機能)
# ========================================

@require_http_methods(["POST"])
def add_stamp(request, transcript_id):
    """文字起こしにスタンプを追加"""
    try:
        transcript = get_object_or_404(Transcript, id=transcript_id)
        data = json.loads(request.body)
        stamp_type = data.get('stamp_type')
        
        if not stamp_type:
            return JsonResponse({'status': 'error', 'message': 'stamp_type is required'}, status=400)
        
        # 既存のスタンプがあれば削除
        TranscriptStamp.objects.filter(transcript=transcript, stamp_type=stamp_type).delete()
        
        # 新しいスタンプを作成
        stamp = TranscriptStamp.objects.create(
            transcript=transcript,
            stamp_type=stamp_type,
            created_by=request.user if request.user.is_authenticated else None
        )
        
        return JsonResponse({
            'status': 'success',
            'stamp_id': stamp.id,
            'stamp_type': stamp.stamp_type,
            'stamp_display': stamp.get_stamp_type_display()
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_http_methods(["DELETE"])
def remove_stamp(request, stamp_id):
    """スタンプを削除"""
    try:
        stamp = get_object_or_404(TranscriptStamp, id=stamp_id)
        stamp.delete()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_http_methods(["GET"])
def get_transcript_stamps(request, transcript_id):
    """トランスクリプトのスタンプ一覧を取得"""
    try:
        transcript = get_object_or_404(Transcript, id=transcript_id)
        stamps = TranscriptStamp.objects.filter(transcript=transcript)
        
        stamps_data = [
            {
                'id': stamp.id,
                'stamp_type': stamp.stamp_type,
                'stamp_display': stamp.get_stamp_type_display(),
                'created_at': stamp.created_at.isoformat()
            }
            for stamp in stamps
        ]
        
        return JsonResponse({'status': 'success', 'stamps': stamps_data})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ========================================
# Transcript Comment API (コメント機能)
# ========================================

@require_http_methods(["POST"])
def add_comment(request, transcript_id):
    """文字起こしにコメントを追加"""
    try:
        transcript = get_object_or_404(Transcript, id=transcript_id)
        data = json.loads(request.body)
        comment_text = data.get('comment_text', '').strip()
        
        if not comment_text:
            return JsonResponse({'status': 'error', 'message': 'comment_text is required'}, status=400)
        
        comment = TranscriptComment.objects.create(
            transcript=transcript,
            comment_text=comment_text,
            created_by=request.user if request.user.is_authenticated else None
        )
        
        return JsonResponse({
            'status': 'success',
            'comment_id': comment.id,
            'comment_text': comment.comment_text,
            'created_at': comment.created_at.isoformat()
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_http_methods(["POST"])
def edit_comment(request, comment_id):
    """コメントを編集"""
    try:
        comment = get_object_or_404(TranscriptComment, id=comment_id)
        data = json.loads(request.body)
        comment_text = data.get('comment_text', '').strip()
        
        if not comment_text:
            return JsonResponse({'status': 'error', 'message': 'comment_text is required'}, status=400)
        
        comment.comment_text = comment_text
        comment.save()
        
        return JsonResponse({
            'status': 'success',
            'comment_id': comment.id,
            'comment_text': comment.comment_text,
            'updated_at': comment.updated_at.isoformat()
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_http_methods(["DELETE"])
def delete_comment(request, comment_id):
    """コメントを削除"""
    try:
        comment = get_object_or_404(TranscriptComment, id=comment_id)
        comment.delete()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_http_methods(["GET"])
def get_transcript_comments(request, transcript_id):
    """トランスクリプトのコメント一覧を取得"""
    try:
        transcript = get_object_or_404(Transcript, id=transcript_id)
        comments = TranscriptComment.objects.filter(transcript=transcript)
        
        comments_data = [
            {
                'id': comment.id,
                'comment_text': comment.comment_text,
                'created_by': comment.created_by.username if comment.created_by else 'Anonymous',
                'created_at': comment.created_at.isoformat(),
                'updated_at': comment.updated_at.isoformat()
            }
            for comment in comments
        ]
        
        return JsonResponse({'status': 'success', 'comments': comments_data})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ========================================
# Transcript Mark API (マーキング機能)
# ========================================

@require_http_methods(["POST"])
def add_mark(request, transcript_id):
    """文字起こしにマーク（ハイライト）を追加"""
    try:
        transcript = get_object_or_404(Transcript, id=transcript_id)
        data = json.loads(request.body)
        color = data.get('color')
        note = data.get('note', '')
        
        if not color:
            return JsonResponse({'status': 'error', 'message': 'color is required'}, status=400)
        
        # 既存のマークがあれば削除
        TranscriptMark.objects.filter(transcript=transcript, color=color).delete()
        
        # 新しいマークを作成
        mark = TranscriptMark.objects.create(
            transcript=transcript,
            color=color,
            note=note,
            created_by=request.user if request.user.is_authenticated else None
        )
        
        return JsonResponse({
            'status': 'success',
            'mark_id': mark.id,
            'color': mark.color,
            'color_display': mark.get_color_display(),
            'note': mark.note,
            'created_at': mark.created_at.isoformat()
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_http_methods(["DELETE"])
def remove_mark(request, mark_id):
    """マークを削除"""
    try:
        mark = get_object_or_404(TranscriptMark, id=mark_id)
        mark.delete()
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_http_methods(["POST"])
def edit_mark(request, mark_id):
    """マークを編集（ノート更新）"""
    try:
        mark = get_object_or_404(TranscriptMark, id=mark_id)
        data = json.loads(request.body)
        note = data.get('note', '')
        
        mark.note = note
        mark.save()
        
        return JsonResponse({
            'status': 'success',
            'mark_id': mark.id,
            'note': mark.note,
            'updated_at': mark.updated_at.isoformat()
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_http_methods(["GET"])
def get_transcript_marks(request, transcript_id):
    """トランスクリプトのマーク一覧を取得"""
    try:
        transcript = get_object_or_404(Transcript, id=transcript_id)
        marks = TranscriptMark.objects.filter(transcript=transcript)
        
        marks_data = [
            {
                'id': mark.id,
                'color': mark.color,
                'color_display': mark.get_color_display(),
                'note': mark.note,
                'created_at': mark.created_at.isoformat(),
                'updated_at': mark.updated_at.isoformat()
            }
            for mark in marks
        ]
        
        return JsonResponse({'status': 'success', 'marks': marks_data})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)