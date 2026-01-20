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
    path('readme/', views.readme, name='readme'),
]