from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('create/', views.create_meeting, name='create_meeting'),
    path('meeting/<int:meeting_id>/', views.meeting_room, name='meeting_room'),
    path('meeting/<int:meeting_id>/detail/', views.meeting_detail, name='meeting_detail'),
]