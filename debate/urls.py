from django.urls import path
from . import views

urlpatterns = [
    path('', views.debate_index, name='debate_index'),
    path('create/', views.debate_create, name='debate_create'),
    path('<int:debate_id>/', views.debate_room, name='debate_room'),
    path('<int:debate_id>/detail/', views.debate_detail, name='debate_detail'),
    path('<int:debate_id>/delete/', views.delete_debate, name='delete_debate'),
    
    # Debate API
    path('<int:debate_id>/statement/add/', views.save_debate_statement, name='save_debate_statement'),
    path('<int:debate_id>/ai-response/', views.get_ai_response, name='get_ai_response'),
    path('<int:debate_id>/judge/', views.judge_debate, name='judge_debate'),
    
    # Speech-to-Text API
    path('transcribe/', views.transcribe_audio, name='transcribe_audio'),
]
