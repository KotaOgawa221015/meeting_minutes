import json
import base64
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from openai import OpenAI
from django.conf import settings
from .models import Meeting, Transcript
import tempfile
import os


class MeetingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.meeting_id = self.scope['url_route']['kwargs']['meeting_id']
        self.room_group_name = f'meeting_{self.meeting_id}'
        
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # 音声バッファ
        self.audio_buffer = []
        self.buffer_duration = 5

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        message_type = data.get('type')

        if message_type == 'audio_chunk':
            audio_data = data.get('audio')
            await self.process_audio_chunk(audio_data)
        
        elif message_type == 'stop_recording':
            await self.finalize_transcription()

    async def process_audio_chunk(self, audio_base64):
        """音声チャンクを処理してWhisper APIに送信"""
        try:
            audio_bytes = base64.b64decode(audio_base64)
            self.audio_buffer.append(audio_bytes)
            
            # バッファが十分溜まったら処理
            if len(self.audio_buffer) >= 10:
                combined_audio = b''.join(self.audio_buffer)
                self.audio_buffer = []
                
                # 一時ファイルに保存（拡張子を.mp3に変更）
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                    temp_file.write(combined_audio)
                    temp_file_path = temp_file.name
                
                # Whisper APIで文字起こし
                transcript_text = await self.transcribe_audio(temp_file_path)
                
                # 一時ファイル削除
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                
                if transcript_text:
                    await self.save_transcript(transcript_text)
                    
                    await self.send(text_data=json.dumps({
                        'type': 'transcript',
                        'text': transcript_text
                    }))
        
        except Exception as e:
            print(f"Audio processing error: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'音声処理エラー: {str(e)}'
            }))

    async def transcribe_audio(self, audio_file_path):
        """Whisper APIで音声をテキストに変換"""
        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            
            with open(audio_file_path, 'rb') as audio_file:
                transcript = await asyncio.to_thread(
                    client.audio.transcriptions.create,
                    model="whisper-1",
                    file=audio_file,
                    language="ja",
                    response_format="text"
                )
            return transcript
        except Exception as e:
            print(f"Whisper API error: {e}")
            return None

    @database_sync_to_async
    def save_transcript(self, text):
        """文字起こしをデータベースに保存"""
        meeting = Meeting.objects.get(id=self.meeting_id)
        Transcript.objects.create(
            meeting=meeting,
            text=text,
            timestamp=meeting.transcripts.count() * 5
        )

    async def finalize_transcription(self):
        """録音終了時の最終処理"""
        if self.audio_buffer:
            combined_audio = b''.join(self.audio_buffer)
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                temp_file.write(combined_audio)
                temp_file_path = temp_file.name
            
            transcript_text = await self.transcribe_audio(temp_file_path)
            try:
                os.unlink(temp_file_path)
            except:
                pass
            
            if transcript_text:
                await self.save_transcript(transcript_text)
        
        # 議事録要約を生成
        await self.generate_summary()

    async def generate_summary(self):
        """GPT-4で議事録要約を生成"""
        transcripts = await self.get_all_transcripts()
        full_text = "\n".join([t.text for t in transcripts])
        
        if not full_text:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': '文字起こしデータがありません'
            }))
            return
        
        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model="gpt-4o-mini",  # JSON対応モデルに変更
                messages=[
                    {
                        "role": "system",
                        "content": """あなたは議事録作成の専門家です。
会議の文字起こしから、以下の形式のJSON形式で議事録を作成してください。
必ずJSON形式のみを返し、他の説明文や説明は一切含めないでください。

{
  "summary": "会議全体の要約（2-3文）",
  "key_points": ["重要ポイント1", "重要ポイント2", "重要ポイント3"],
  "action_items": [
    {"task": "具体的なタスク内容", "assignee": "担当者名（不明な場合は空文字）"}
  ],
  "decisions": ["決定事項1", "決定事項2"]
}"""
                    },
                    {
                        "role": "user",
                        "content": f"以下の会議内容から議事録を作成してください：\n\n{full_text}"
                    }
                ],
                temperature=0.3,
                response_format={ "type": "json_object" }
            )
            
            # レスポンスからJSONを取得
            response_text = response.choices[0].message.content.strip()
            print(f"GPT Response: {response_text}")  # デバッグ用
            
            # JSONパース
            summary_json = json.loads(response_text)
            
            await self.save_summary(full_text, summary_json)
            
            await self.send(text_data=json.dumps({
                'type': 'summary_complete',
                'summary': summary_json
            }))
        
        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            print(f"Response was: {response_text if 'response_text' in locals() else 'No response'}")
            
            # フォールバック: 簡易要約
            fallback_summary = {
                "summary": "議事録の自動生成に失敗しました。",
                "key_points": [full_text[:200] + "..."] if len(full_text) > 200 else [full_text],
                "action_items": [],
                "decisions": []
            }
            await self.save_summary(full_text, fallback_summary)
            await self.send(text_data=json.dumps({
                'type': 'summary_complete',
                'summary': fallback_summary
            }))
        
        except Exception as e:
            print(f"Summary generation error: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'要約生成エラー: {str(e)}'
            }))

    @database_sync_to_async
    def get_all_transcripts(self):
        meeting = Meeting.objects.get(id=self.meeting_id)
        return list(meeting.transcripts.all())

    @database_sync_to_async
    def save_summary(self, full_text, summary_data):
        from .models import MinuteSummary
        meeting = Meeting.objects.get(id=self.meeting_id)
        
        MinuteSummary.objects.update_or_create(
            meeting=meeting,
            defaults={
                'full_transcript': full_text,
                'summary': summary_data.get('summary', ''),
                'key_points': summary_data.get('key_points', []),
                'action_items': summary_data.get('action_items', []),
                'decisions': summary_data.get('decisions', [])
            }
        )
        
        meeting.status = 'completed'
        meeting.save()