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


def readme(request):
    """READMEページ"""
    return render(request, 'minutes/readme.html')