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
        duration_minutes = request.POST.get('duration_minutes', 60)
        use_facilitator = request.POST.get('use_facilitator') == 'on'
        
        # 分を秒に変換
        try:
            duration_seconds = int(duration_minutes) * 60
        except (ValueError, TypeError):
            duration_seconds = 60 * 60  # デフォルト60分
        
        meeting = Meeting.objects.create(
            title=title,
            created_by=request.user if request.user.is_authenticated else None,
            status='recording',
            duration_seconds=duration_seconds,
            use_facilitator=use_facilitator
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


def readme(request):
    """READMEページ"""
    return render(request, 'minutes/readme.html')