#!/usr/bin/env python
"""Check VoiceVox speakers returned by API"""
import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'meeting_minutes.settings')
django.setup()

from minutes.views import voicevox_speakers
from django.test import RequestFactory

factory = RequestFactory()
request = factory.get('/voicevox/speakers/')
response = voicevox_speakers(request)

data = json.loads(response.content)
print('VoiceVox Speakers Response:')
if data.get('status') == 'success':
    speakers = data.get('speakers', [])
    print(f'Total speakers: {len(speakers)}')
    for i, speaker in enumerate(speakers):
        print(f'{i+1}. {speaker.get("name")}: id={speaker.get("id")}')
else:
    print('Error:', data.get('message'))
