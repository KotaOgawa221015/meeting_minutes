from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('create/', views.create_meeting, name='create_meeting'),
    path('meeting/<int:meeting_id>/', views.meeting_room, name='meeting_room'),
    path('meeting/<int:meeting_id>/detail/', views.meeting_detail, name='meeting_detail'),
    path('meeting/<int:meeting_id>/delete/', views.delete_meeting, name='delete_meeting'),
    path('meeting/<int:meeting_id>/end/', views.end_meeting, name='end_meeting'),
    path('meeting/<int:meeting_id>/status/', views.get_meeting_status, name='get_meeting_status'),
    path('meeting/<int:meeting_id>/data/', views.get_meeting_data, name='get_meeting_data'),
    path('meeting/<int:meeting_id>/save-transcript/', views.save_manual_transcript, name='save_manual_transcript'),
    path('readme/', views.readme, name='readme'),
    
    # Transcript Stamp API
    path('transcript/<int:transcript_id>/stamp/add/', views.add_stamp, name='add_stamp'),
    path('stamp/<int:stamp_id>/remove/', views.remove_stamp, name='remove_stamp'),
    path('transcript/<int:transcript_id>/stamps/', views.get_transcript_stamps, name='get_transcript_stamps'),
    
    # Transcript Comment API
    path('transcript/<int:transcript_id>/comment/add/', views.add_comment, name='add_comment'),
    path('comment/<int:comment_id>/edit/', views.edit_comment, name='edit_comment'),
    path('comment/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
    path('transcript/<int:transcript_id>/comments/', views.get_transcript_comments, name='get_transcript_comments'),
    
    # Transcript Mark API
    path('transcript/<int:transcript_id>/mark/add/', views.add_mark, name='add_mark'),
    path('mark/<int:mark_id>/remove/', views.remove_mark, name='remove_mark'),
    path('mark/<int:mark_id>/edit/', views.edit_mark, name='edit_mark'),
    path('transcript/<int:transcript_id>/marks/', views.get_transcript_marks, name='get_transcript_marks'),
    
    # AI Member API
    path('meeting/<int:meeting_id>/add-ai-member/', views.add_ai_member, name='add_ai_member'),
    path('meeting/<int:meeting_id>/ai-members/', views.get_ai_members, name='get_ai_members'),
    path('ai-member/<int:ai_member_id>/delete/', views.delete_ai_member, name='delete_ai_member'),
    path('ai-member/<int:ai_member_id>/rename/', views.rename_ai_member, name='rename_ai_member'),
    path('meeting/<int:meeting_id>/delete-all-ai-members/', views.delete_all_ai_members, name='delete_all_ai_members'),
    path('meeting/<int:meeting_id>/rename-speaker/', views.rename_speaker, name='rename_speaker'),

    # TTS (VOICEVOX) Proxy API
    path('tts/ping/', views.tts_ping, name='tts_ping'),
    path('tts/speak/', views.tts_speak, name='tts_speak'),
    path('tts/diagnose/', views.tts_diagnose, name='tts_diagnose'),
]
