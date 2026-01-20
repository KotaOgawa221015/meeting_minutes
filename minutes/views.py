from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from .models import Meeting, MinuteSummary

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