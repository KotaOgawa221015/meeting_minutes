#!/usr/bin/env python
"""Check voicevox_speakers API response"""
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'meeting_minutes.settings')
django.setup()

from minutes.views import voicevox_speakers
from django.test import RequestFactory
from django.conf import settings

# Add testserver to ALLOWED_HOSTS
if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append('testserver')

factory = RequestFactory()
request = factory.get('/voicevox/speakers/')
response = voicevox_speakers(request)
data = json.loads(response.content)

if data.get('status') == 'success':
    speakers = data.get('speakers', [])
    print(f'Total speakers: {len(speakers)}')
    for i, speaker in enumerate(speakers[:3]):
        print(f'{i+1}. Name: {speaker.get("name")}')
        print(f'   ID: {speaker.get("id")}')
        print(f'   Keys: {list(speaker.keys())}')
        print()
else:
    print('Error:', data)
