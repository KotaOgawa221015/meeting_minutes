#!/usr/bin/env python
"""Test add_ai_member API with different speaker IDs"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'meeting_minutes.settings')
django.setup()

# Add testserver to ALLOWED_HOSTS
from django.conf import settings
if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append('testserver')

import json
from django.test import Client
from minutes.models import Meeting, AIMember

# Get first meeting
meeting = Meeting.objects.first()
if not meeting:
    print("No meeting found!")
    exit(1)

client = Client()

# First, clear the debug log
if os.path.exists('debug_add_ai_member.log'):
    with open('debug_add_ai_member.log', 'w', encoding='utf-8') as f:
        f.write('')

# Test 1: Send ID 3
print("Test 1: Sending voicevox_speaker_id=3 (ずんだもん)")
request_data = {
    'personality': 'idea',
    'count': 1,
    'voicevox_speaker_id': 3,
    'voicevox_style_id': 0,
    'voicevox_speed': 1.0,
    'voicevox_pitch': 0.0
}
print(f"Request body: {json.dumps(request_data)}")

response = client.post(
    f'/meeting/{meeting.id}/add-ai-member/',
    data=json.dumps(request_data),
    content_type='application/json'
)
print(f"Response status: {response.status_code}")

# Check the debug log
import time
time.sleep(0.1)
if os.path.exists('debug_add_ai_member.log'):
    with open('debug_add_ai_member.log', 'r', encoding='utf-8') as f:
        log_content = f.read()
    if log_content:
        print("\nDebug log content:")
        print(log_content)
    else:
        print("\nDebug log is empty - add_ai_member may not have been called")
else:
    print("\nDebug log file not created")

# Check what was saved
last_member = AIMember.objects.order_by('-id').first()
if last_member:
    print(f"Latest AI member saved with speaker_id: {last_member.voicevox_speaker_id}")
