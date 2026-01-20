#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'meeting_minutes.settings')
django.setup()

from minutes.models import Meeting, MinuteSummary

# 最新の会議を取得
meeting = Meeting.objects.last()
if meeting:
    print(f'Meeting ID: {meeting.id}')
    print(f'Meeting Title: {meeting.title}')
    print(f'Meeting Status: {meeting.status}')
    
    try:
        summary = meeting.summary
        print(f'Summary exists: True')
        print(f'Summary text (first 100 chars): {summary.summary[:100]}')
        print(f'Key points: {summary.key_points}')
        print(f'Action items: {summary.action_items}')
        print(f'Decisions: {summary.decisions}')
    except MinuteSummary.DoesNotExist:
        print('Summary exists: False')
else:
    print('No meetings found')
