import json
import base64
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from openai import OpenAI
from django.conf import settings
from django.utils import timezone
from datetime import datetime
from .models import Meeting, Transcript
import tempfile
import os
import time
import subprocess
from datetime import datetime


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
        self.chunk_count = 0
        self.start_time = time.time()
        
        # --- 追加: WebMヘッダー保持用の変数 ---
        self.webm_header = None
        self.is_first_process = True
        # ------------------------------------
        
        # ファシリテーター機能（オプショナル）
        self.facilitator_task = None
        self.last_phase = None  # 初期状態はNoneに設定
        
        # 会議開始時間をDBに保存
        await self.set_meeting_start_time()
        
        # ファシリテータースケジュールを開始（有効化されている場合）
        meeting = await self.get_meeting()
        if meeting.use_facilitator and meeting.duration_seconds > 0:
            self.facilitator_task = asyncio.create_task(self.facilitator_loop())
            # 初期フェーズを即座にチェック
            await self.check_progress_and_facilitate()
            print(f"[Meeting {self.meeting_id}] AIファシリテーター機能: 有効")
        else:
            print(f"[Meeting {self.meeting_id}] AIファシリテーター機能: 無効")
        
        print(f"[Meeting {self.meeting_id}] WebSocket接続成功")

    async def disconnect(self, close_code):
        if self.facilitator_task:
            self.facilitator_task.cancel()
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        print(f"[Meeting {self.meeting_id}] WebSocket切断")

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
            
            # --- 追加: 最初のチャンクからヘッダー情報を保存 ---
            # これがないと2回目以降の変換で「Invalid data」エラーになる
            if self.webm_header is None and len(audio_bytes) > 0:
                self.webm_header = audio_bytes
                print(f"[Meeting {self.meeting_id}] WebMヘッダー情報を保存しました")
            # ------------------------------------------------
            
            self.audio_buffer.append(audio_bytes)
            self.chunk_count += 1
            
            print(f"[Meeting {self.meeting_id}] 音声チャンク受信: {self.chunk_count}個目 ({len(audio_bytes)} bytes)")
            
            # 5秒分のチャンク（約10個）が溜まったら処理
            if len(self.audio_buffer) >= 10:
                print(f"[Meeting {self.meeting_id}] 文字起こし開始 ({len(self.audio_buffer)}チャンク)")
                
                combined_audio = b''.join(self.audio_buffer)
                self.audio_buffer = []  # バッファクリア
                
                if len(combined_audio) < 1000:
                    return
                
                # --- 修正: 保存するデータの作成 ---
                # 2回目以降の処理なら、保存しておいたヘッダーを先頭に結合する
                final_audio_data = combined_audio
                
                if not self.is_first_process:
                    if self.webm_header:
                        print(f"[Meeting {self.meeting_id}] ヘッダーを付与して保存します")
                        final_audio_data = self.webm_header + combined_audio
                else:
                    self.is_first_process = False
                # ----------------------------------

                # 一時ファイルに保存（WebM）
                temp_webm_path = None
                temp_mp3_path = None
                success = False
                
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_file:
                        temp_file.write(final_audio_data) # combined_audio ではなく final_audio_data を使う
                        temp_webm_path = temp_file.name
                    
                    print(f"[Meeting {self.meeting_id}] 一時WebMファイル作成: {temp_webm_path}")
                    
                    # WebMをMP3に変換
                    temp_mp3_path = temp_webm_path.replace('.webm', '.mp3')
                    success = await self.convert_to_mp3(temp_webm_path, temp_mp3_path)
                    
                    # --- 以下、前回の修正版 finalize_transcription と同様のロジック ---
                    transcript_text = None
                    if success:
                        transcript_text = await self.transcribe_audio(temp_mp3_path)
                    
                    # クリーンアップ
                    try:
                        if temp_webm_path and os.path.exists(temp_webm_path):
                            os.unlink(temp_webm_path)
                        if temp_mp3_path and os.path.exists(temp_mp3_path):
                            os.unlink(temp_mp3_path)
                    except:
                        pass
                    
                    if transcript_text and len(transcript_text.strip()) > 0:
                        elapsed_time = time.time() - self.start_time
                        print(f"[Meeting {self.meeting_id}] 文字起こし成功: {transcript_text[:50]}...")
                        await self.save_transcript(transcript_text, elapsed_time)
                        await self.send(text_data=json.dumps({
                            'type': 'transcript',
                            'text': transcript_text,
                            'timestamp': elapsed_time
                        }))
                
                except Exception as e:
                    print(f"処理中の予期せぬエラー: {e}")
                    import traceback
                    traceback.print_exc()

        except Exception as e:
            print(f"[Meeting {self.meeting_id}] 音声処理エラー: {e}")
            import traceback
            traceback.print_exc()
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'音声処理エラー: {str(e)}'
            }))
            
    async def transcribe_audio(self, audio_file_path):
        """Whisper APIで音声をテキストに変換"""
        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            
            print(f"[Meeting {self.meeting_id}] Whisper API呼び出し中...")
            print(f"[Meeting {self.meeting_id}] ファイルサイズ: {os.path.getsize(audio_file_path)} bytes")
            
            with open(audio_file_path, 'rb') as audio_file:
                transcript = await asyncio.to_thread(
                    client.audio.transcriptions.create,
                    model="whisper-1",
                    file=audio_file,
                    language="ja",
                    response_format="text"
                )

            text = transcript.strip()
            forbidden_words = [
                "ご視聴",
                "チャンネル登録",
                "ブーブー",
                "最後までご覧",
                "本日はご覧",
                "はじめしゃちょー"
            ] # 排除したいワードのリスト

            # 禁止文字が含まれているかチェック
            if any(word in text for word in forbidden_words):
                print(f"[Meeting {self.meeting_id}] 禁止文字を検知したため、この発言を破棄します")
                return None # Noneを返却することで、保存・送信プロセスを中断させる
                
            print(f"[Meeting {self.meeting_id}] Whisper API成功")
            return transcript.strip() if transcript else None
            
        except Exception as e:
            print(f"[Meeting {self.meeting_id}] Whisper API error: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def convert_to_mp3(self, input_path, output_path):
        """ffmpegを使ってWebMをMP3に変換 (Windows対応・修正版)"""
        try:
            print(f"[Meeting {self.meeting_id}] ffmpeg変換開始: {input_path} -> {output_path}")
            
            # ffmpegコマンド
            command = [
                'ffmpeg',
                '-i', input_path,
                '-vn',  # 動画なし
                '-ar', '44100',  # サンプルレート
                '-ac', '2',  # ステレオ
                '-b:a', '192k',  # ビットレート
                '-y',  # 上書き
                output_path
            ]
            
            # --- 重要な変更点ここから ---
            # Windowsのasyncio問題回避のため、同期処理(subprocess.run)を
            # asyncio.to_threadを使って別スレッドで実行します。
            
            def run_ffmpeg():
                return subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False
                )

            # ここで古い create_subprocess_exec は使いません
            process = await asyncio.to_thread(run_ffmpeg)
            # --- 重要な変更点ここまで ---
            
            if process.returncode == 0:
                print(f"[Meeting {self.meeting_id}] ffmpeg変換成功")
                return True
            else:
                # stderrのデコード処理
                error_message = process.stderr.decode('utf-8', errors='ignore')
                print(f"[Meeting {self.meeting_id}] ffmpeg変換失敗: {error_message}")
                return False
                
        except FileNotFoundError:
            print(f"[Meeting {self.meeting_id}] ffmpegが見つかりません。インストールしてください。")
            return False
        except Exception as e:
            print(f"[Meeting {self.meeting_id}] ffmpeg変換エラー: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def facilitator_loop(self):
        """ファシリテーターのメインループ"""
        try:
            # 会議時間に応じてチェック間隔を調整
            meeting = await self.get_meeting()
            check_interval = max(5, min(30, meeting.duration_seconds // 20))  # 5～30秒
            print(f"[Meeting {self.meeting_id}] ファシリテーター: チェック間隔 {check_interval}秒")
            
            while True:
                await asyncio.sleep(check_interval)
                await self.check_progress_and_facilitate()
        except asyncio.CancelledError:
            print(f"[Meeting {self.meeting_id}] ファシリテーターループ終了")
            raise
    
    async def check_progress_and_facilitate(self):
        """進行状況をチェックしてファシリテート"""
        try:
            meeting = await self.get_meeting()
            if not meeting.start_time or meeting.duration_seconds <= 0:
                return
            
            elapsed = (timezone.now() - meeting.start_time).total_seconds()
            progress = (elapsed / meeting.duration_seconds) * 100
            
            # 100%を超えた場合はcap
            progress = min(progress, 100.0)
            
            # 現在のフェーズを決定
            current_phase = self.get_phase_from_progress(progress)
            
            # 初回チェックまたはフェーズが変更された場合
            if current_phase != self.last_phase:
                phase_names = {
                    'introduction': '導入',
                    'sharing': '共有',
                    'discussion': '議論',
                    'summary': 'まとめ'
                }
                prev_phase = phase_names.get(self.last_phase, 'なし')
                print(f"[Meeting {self.meeting_id}] フェーズ変更: {prev_phase} -> {phase_names.get(current_phase)} (進行状況: {progress:.1f}%)")
                self.last_phase = current_phase
                await self.update_meeting_phase(current_phase)
                await self.facilitate(current_phase, progress)
                
        except Exception as e:
            print(f"[Meeting {self.meeting_id}] ファシリテートチェックエラー: {e}")
            import traceback
            traceback.print_exc()
    
    def get_phase_from_progress(self, progress):
        """進行状況からフェーズを決定"""
        if progress < 10:
            return 'introduction'
        elif progress < 25:
            return 'sharing'
        elif progress < 85:
            return 'discussion'
        else:
            return 'summary'
        
    async def facilitate(self, phase, progress):
        """フェーズに基づいてファシリテート"""
        try:
            transcripts = await self.get_all_transcripts()
            if not transcripts:
                return
            
            # 最新のログを取得（直近5分以内）
            recent_transcripts = [t for t in transcripts if t.timestamp > (time.time() - self.start_time - 300)]
            full_text = "\n".join([f"[{t.timestamp:.0f}秒] {t.text}" for t in recent_transcripts])
            
            phase_descriptions = {
                'introduction': '導入 (10%): 目的の再確認、ゴールの共有、アイスブレイク',
                'sharing': '共有(15%): 議論に必要な前提知識やデータのクイックな共有',
                'discussion': '議論(60%): メインパート。アイデア出し、課題解決、意思決定',
                'summary': 'まとめ(15%): 決定事項の確認、Next Action（誰が・いつまでに）の特定'
            }
            
            prompt = f"""
あなたは会議のファシリテーターです。現在のフェーズ: {phase_descriptions[phase]}
進行状況: {progress:.1f}%

これまでの会話ログ:
{full_text}

このフェーズの目的に基づいて、会議を効果的に進めるための短い介入メッセージを作成してください。
メッセージは簡潔に、建設的で、参加者を励ますものにしてください。
JSON形式で返してください: {{"message": "介入メッセージ"}}
"""
            
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            message = result.get('message', '')
            
            if message:
                await self.send(text_data=json.dumps({
                    'type': 'facilitator_message',
                    'message': message,
                    'phase': phase,
                    'progress': progress
                }))
                print(f"[Meeting {self.meeting_id}] ファシリテーターメッセージ: {message}")
                
        except Exception as e:
            print(f"[Meeting {self.meeting_id}] ファシリテートエラー: {e}")

    async def finalize_transcription(self):
        """録音終了時の最終処理"""
        print(f"[Meeting {self.meeting_id}] 録音終了処理開始")
        
        # 残りのバッファを処理
        if self.audio_buffer and len(self.audio_buffer) > 0:
            print(f"[Meeting {self.meeting_id}] 残りバッファ処理: {len(self.audio_buffer)}チャンク")
            
            combined_audio = b''.join(self.audio_buffer)
            
            # 変数を初期化（UnboundLocalError防止）
            transcript_text = None
            
            if len(combined_audio) >= 1000:  # 1KB以上なら処理
                temp_webm_path = None
                temp_mp3_path = None
                success = False

                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_file:
                        temp_file.write(combined_audio)
                        temp_webm_path = temp_file.name
                    
                    # WebMをMP3に変換
                    temp_mp3_path = temp_webm_path.replace('.webm', '.mp3')
                    success = await self.convert_to_mp3(temp_webm_path, temp_mp3_path)
                    
                    if success:
                        transcript_text = await self.transcribe_audio(temp_mp3_path)
                
                except Exception as e:
                    print(f"[Meeting {self.meeting_id}] 最終処理中のエラー: {e}")
                
                finally:
                    # クリーンアップ処理
                    try:
                        if temp_webm_path and os.path.exists(temp_webm_path):
                            os.unlink(temp_webm_path)
                        if temp_mp3_path and os.path.exists(temp_mp3_path):
                            os.unlink(temp_mp3_path)
                    except Exception as e:
                        print(f"ファイル削除エラー: {e}")
                
                # 文字起こし結果があれば保存
                if transcript_text and len(transcript_text.strip()) > 0:
                    elapsed_time = time.time() - self.start_time
                    await self.save_transcript(transcript_text, elapsed_time)
        
        # 議事録要約を生成
        await self.generate_summary()

    async def generate_summary(self):
        """GPT-4で議事録要約を生成"""
        print(f"[Meeting {self.meeting_id}] 議事録要約生成開始")
        
        transcripts = await self.get_all_transcripts()
        
        if not transcripts or len(transcripts) == 0:
            print(f"[Meeting {self.meeting_id}] 文字起こしデータなし")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': '文字起こしデータがありません'
            }))
            return
        
        # タイムスタンプ順に並べて全文を結合
        sorted_transcripts = sorted(transcripts, key=lambda t: t.timestamp)
        full_text = "\n".join([f"[{t.timestamp:.0f}秒] {t.text}" for t in sorted_transcripts])
        
        print(f"[Meeting {self.meeting_id}] 全文字起こし: {len(sorted_transcripts)}セグメント, {len(full_text)}文字")
        
        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            
            print(f"[Meeting {self.meeting_id}] GPT-4呼び出し中...")
            
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """あなたは議事録作成の専門家です。
会議の文字起こしから、以下の形式のJSON形式で議事録を作成してください。
必ずJSON形式のみを返し、他の説明文や説明は一切含めないでください。

{
  "summary": "会議全体の要約（3-5文で具体的に）",
  "key_points": ["重要ポイント1", "重要ポイント2", "重要ポイント3"],
  "action_items": [
    {"task": "具体的なタスク内容", "assignee": "担当者名（不明な場合は空文字）"}
  ],
  "decisions": ["決定事項1", "決定事項2"]
}

文字起こしは時系列順に並んでいます。[X秒]の形式でタイムスタンプが付いています。
会話の流れを理解して、重要な内容を抽出してください。"""
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
            print(f"[Meeting {self.meeting_id}] GPT Response: {response_text[:200]}...")
            
            # JSONパース
            summary_json = json.loads(response_text)
            
            await self.save_summary(full_text, summary_json)
            
            print(f"[Meeting {self.meeting_id}] 議事録生成完了")
            
            await self.send(text_data=json.dumps({
                'type': 'summary_complete',
                'summary': summary_json
            }))
        
        except json.JSONDecodeError as e:
            print(f"[Meeting {self.meeting_id}] JSON parse error: {e}")
            
            # フォールバック: 簡易要約
            fallback_summary = {
                "summary": f"会議で{len(sorted_transcripts)}個の発言がありました。",
                "key_points": [t.text[:100] + "..." if len(t.text) > 100 else t.text for t in sorted_transcripts[:5]],
                "action_items": [],
                "decisions": []
            }
            await self.save_summary(full_text, fallback_summary)
            await self.send(text_data=json.dumps({
                'type': 'summary_complete',
                'summary': fallback_summary
            }))
        
        except Exception as e:
            print(f"[Meeting {self.meeting_id}] Summary generation error: {e}")
            import traceback
            traceback.print_exc()
            
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': f'要約生成エラー: {str(e)}'
            }))

    @database_sync_to_async
    def get_all_transcripts(self):
        meeting = Meeting.objects.get(id=self.meeting_id)
        return list(meeting.transcripts.all())

    @database_sync_to_async
    def save_transcript(self, text, timestamp):
        """文字起こしをデータベースに保存"""
        meeting = Meeting.objects.get(id=self.meeting_id)
        Transcript.objects.create(
            meeting=meeting,
            text=text,
            timestamp=timestamp
        )
        print(f"[Meeting {self.meeting_id}] DB保存完了: timestamp={timestamp:.1f}秒")

    @database_sync_to_async
    def set_meeting_start_time(self):
        meeting = Meeting.objects.get(id=self.meeting_id)
        if not meeting.start_time:
            meeting.start_time = timezone.now()
            meeting.save()
        print(f"[Meeting {self.meeting_id}] 会議開始時間設定: {meeting.start_time}")

    @database_sync_to_async
    def get_meeting(self):
        return Meeting.objects.get(id=self.meeting_id)
    
    @database_sync_to_async
    def update_meeting_phase(self, phase):
        meeting = Meeting.objects.get(id=self.meeting_id)
        meeting.current_phase = phase
        meeting.save()

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
        
        print(f"[Meeting {self.meeting_id}] 議事録DB保存完了")