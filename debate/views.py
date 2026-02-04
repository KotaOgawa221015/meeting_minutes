from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
import random
import os
import requests
from .models import Debate, DebateStatement

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# プロキシ設定がない環境でのタイムアウトを防ぐため、プロキシ無効化セッションを作成
# システムのプロキシ設定を無視してローカル接続を高速化
def _get_voicevox_session():
    """VOICEVOX用のプロキシ無効化セッションを取得"""
    session = requests.Session()
    session.trust_env = False  # 環境変数のプロキシ設定を無視
    session.proxies = {'http': None, 'https': None}
    return session


def debate_index(request):
    """ディベート一覧"""
    debates = Debate.objects.only('id', 'title', 'created_at', 'status', 'ai_type').order_by('-created_at')
    return render(request, 'debate/index.html', {'debates': debates})


def debate_create(request):
    """新しいディベートを作成"""
    if request.method == 'POST':
        title = request.POST.get('title', 'テーマなし')
        ai_type = request.POST.get('ai_type', 'logical')
        max_turns = int(request.POST.get('max_turns', 3))
        
        # 先攻後攻を自動決定（50%の確率）
        first_speaker = random.choice(['user', 'ai'])
        
        debate = Debate.objects.create(
            title=title,
            ai_type=ai_type,
            max_turns=max_turns,
            created_by=request.user if request.user.is_authenticated else None,
            status='setup',
            first_speaker=first_speaker  # 作成時に設定
        )
        
        return redirect('debate_room', debate_id=debate.id)
    return render(request, 'debate/create.html')


def debate_room(request, debate_id):
    """ディベートルーム"""
    debate = get_object_or_404(Debate, id=debate_id)
    return render(request, 'debate/room.html', {
        'debate': debate,
        'ai_types': Debate.AI_TYPE_CHOICES
    })


def debate_detail(request, debate_id):
    """ディベート詳細"""
    debate = get_object_or_404(Debate, id=debate_id)
    statements = debate.statements.order_by('order').values('id', 'speaker', 'text', 'order', 'created_at')
    
    return render(request, 'debate/detail.html', {
        'debate': debate,
        'statements': statements
    })


@csrf_exempt
@require_http_methods(["POST"])
def save_debate_statement(request, debate_id):
    """ディベート発言を保存"""
    try:
        debate = get_object_or_404(Debate, id=debate_id)
        data = json.loads(request.body)
        
        speaker = data.get('speaker')  # 'user' or 'ai'
        text = data.get('text', '')
        
        if not text:
            return JsonResponse({'status': 'error', 'message': '発言内容が空です'}, status=400)
        
        # 発言順序を計算
        order = debate.statements.count() + 1
        
        statement = DebateStatement.objects.create(
            debate=debate,
            speaker=speaker,
            text=text,
            order=order
        )
        
        return JsonResponse({
            'status': 'success',
            'statement_id': statement.id,
            'order': order
        })
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def get_ai_response(request, debate_id):
    """AIの返答を生成"""
    try:
        debate = get_object_or_404(Debate, id=debate_id)
        data = json.loads(request.body)
        
        theme = data.get('theme', '')
        user_statement = data.get('user_statement', '')
        ai_position = data.get('ai_position', None)
        user_position = data.get('user_position', None)
        ai_type = debate.ai_type
        
        # 過去の議論履歴を取得
        debate_history = list(debate.statements.order_by('order').values('speaker', 'text', 'order'))
        
        # AIレスポンスを生成（OpenAI API を使用）
        ai_response = generate_ai_argument(
            theme, 
            user_statement, 
            ai_type,
            ai_position=ai_position,
            user_position=user_position,
            debate_history=debate_history
        )
        
        return JsonResponse({
            'status': 'success',
            'response': ai_response
        })
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def assign_debate_positions(request, debate_id):
    """テーマに基づいて立場を割り振る"""
    try:
        debate = get_object_or_404(Debate, id=debate_id)
        
        # AIにテーマ分析させて立場を割り振る
        user_position, ai_position = assign_positions_ai(debate.title, debate.ai_type)
        
        return JsonResponse({
            'status': 'success',
            'user_position': user_position,
            'ai_position': ai_position,
            'theme': debate.title
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def judge_debate(request, debate_id):
    """ディベート結果を判定"""
    try:
        debate = get_object_or_404(Debate, id=debate_id)
        data = json.loads(request.body)
        
        statements = debate.statements.all().order_by('order')
        
        # AIに勝敗を判定させる
        winner, judgment = judge_debate_ai(
            debate.title,
            debate.ai_type,
            list(statements.values('speaker', 'text', 'order'))
        )
        
        debate.winner = winner
        debate.judgment_text = judgment
        debate.status = 'completed'
        debate.save()
        
        return JsonResponse({
            'status': 'success',
            'winner': winner,
            'judgment': judgment
        })
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def generate_ai_argument(theme, user_statement, ai_type, ai_position=None, user_position=None, debate_history=None):
    """AI論者を生成（OpenAI API を使用）"""
    
    # OpenAI API キーを取得
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key or not OPENAI_AVAILABLE:
        # API キーがない場合はフォールバック
        arguments = {
            'logical': f"ご意見ありがとうございます。「{theme}」についてですが、論理的に考えると、{user_statement}とのお考えに対して、別の視点から見ると...",
            'creative': f"興味深いご指摘です。「{theme}」を創造的に捉えると、{user_statement}に加えて、新しい可能性として...",
            'diplomatic': f"確かなご意見ですね。「{theme}」という点で、{user_statement}とのご見解に共感しつつも、別の立場からは...",
            'aggressive': f"ご指摘ありがとうございます。しかし「{theme}」について、{user_statement}というお考えは根拠が不十分で、むしろ...",
        }
        return arguments.get(ai_type, arguments['logical'])
    
    try:
        client = OpenAI(api_key=api_key)
        
        # AIの立場情報を追加
        position_info = ""
        if ai_position:
            position_info = f"\n\n【重要】あなたの立場は「{ai_position}」です。この立場を最後まで一貫して守ってください。"
            if user_position:
                position_info += f"\n相手（人間）の立場は「{user_position}」です。あなたは相手の立場とは反対の主張をしなければなりません。"
        
        # AIタイプに応じたシステムプロンプトを作成（難易度調整版）
        base_rules = f"""これは人間対AIの討論バトルです。

【絶対に守るべきルール】
1. あなたは「{ai_position if ai_position else 'AI側の立場'}」を支持する立場です。絶対にこの立場を変えないでください。
2. 相手の立場（{user_position if user_position else '人間側の立場'}）に同意してはいけません。
3. 自分の立場と矛盾する発言をしてはいけません。
4. ディベートを楽しむために、相手にも反論の余地を残す議論をしてください。
5. 相手の良い点は認めつつも、自分の立場を主張してください。
6. 回答は200文字程度に収めてください。長すぎる回答は避けてください。
7. 完璧な論破を目指すのではなく、建設的な議論を心がけてください。"""
        
        system_prompts = {
            'logical': f"{base_rules}\n\n【あなたのスタイル】論理的なディベーターとして、根拠を示しながら主張してください。ただし、相手の意見にも一理あることを認めた上で反論してください。",
            'creative': f"{base_rules}\n\n【あなたのスタイル】創造的なディベーターとして、新しい視点を提供してください。相手の発想を尊重しながら、異なる角度からの見方を示してください。",
            'diplomatic': f"{base_rules}\n\n【あなたのスタイル】外交的なディベーターとして、相手の意見を尊重しながら議論してください。相手の良い点を認めた上で、穏やかに自分の立場を主張してください。",
            'aggressive': f"{base_rules}\n\n【あなたのスタイル】情熱的なディベーターとして議論してください。熱意を持って主張しますが、相手を傷つける発言は避けてください。",
        }
        
        system_prompt = system_prompts.get(ai_type, system_prompts['logical'])
        
        # 過去の議論履歴を追加（一貫性のため）
        history_context = ""
        if debate_history and len(debate_history) > 0:
            history_context = "\n\n【これまでの議論の流れ】\n"
            for h in debate_history[-4:]:  # 直近4発言まで
                speaker = "あなた" if h.get('speaker') == 'ai' else "相手"
                history_context += f"{speaker}: {h.get('text', '')[:100]}...\n" if len(h.get('text', '')) > 100 else f"{speaker}: {h.get('text', '')}\n"
        
        # ユーザーの発言がない場合（最初のターン）
        if not user_statement:
            user_message = f"テーマ: {theme}{position_info}\n\nこのテーマについて、あなたの立場「{ai_position if ai_position else 'AI側'}」から最初の意見を述べてください。{history_context}"
        else:
            user_message = f"テーマ: {theme}{position_info}{history_context}\n\n相手の最新の意見: {user_statement}\n\nあなたの立場「{ai_position if ai_position else 'AI側'}」から、この意見に対して反論してください。ただし、完璧な論破ではなく、相手にも反論の余地を残してください。"
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        return response.choices[0].message.content.strip()
    
    except Exception as e:
        print(f"OpenAI API Error: {str(e)}")
        # エラー時はフォールバック
        arguments = {
            'logical': f"ご意見ありがとうございます。「{theme}」についてですが、論理的に考えると...",
            'creative': f"興味深いご指摘です。「{theme}」を創造的に捉えると...",
            'diplomatic': f"確かなご意見ですね。「{theme}」という点で...",
            'aggressive': f"ご指摘ありがとうございます。しかし「{theme}」について...",
        }
        return arguments.get(ai_type, arguments['logical'])


def judge_debate_ai(theme, ai_type, statements):
    """ディベート結果をAIに判定させる（OpenAI API を使用）"""
    
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key or not OPENAI_AVAILABLE:
        # API キーがない場合は簡易版で判定
        user_score = 0
        ai_score = 0
        
        for stmt in statements:
            if stmt['speaker'] == 'user':
                if any(word in stmt['text'] for word in ['理由', '根拠', '証拠', 'なぜなら', 'つまり']):
                    user_score += 1
            else:
                if any(word in stmt['text'] for word in ['論理的', '創造的', '外交的', 'したがって']):
                    ai_score += 1
        
        if user_score > ai_score:
            winner = 'user'
            judgment = f"「{theme}」についてのディベートでは、ユーザーの方がより論理的で説得力のある議論を展開されました。"
        elif ai_score > user_score:
            winner = 'ai'
            judgment = f"「{theme}」についてのディベートでは、AIの方がより多角的で説得力のある議論を展開しました。"
        else:
            winner = 'draw'
            judgment = f"「{theme}」についてのディベートは、両者とも同等レベルの説得力を示しており、引き分けです。"
        
        return winner, judgment
    
    try:
        client = OpenAI(api_key=api_key)
        
        # 発言をフォーマット
        statements_text = "\n".join([
            f"{'ユーザー' if s['speaker'] == 'user' else 'AI'}: {s['text']}"
            for s in statements
        ])
        
        judgment_prompt = f"""
以下のディベートについて、客観的に勝敗を判定してください。

テーマ: {theme}
ディベート内容:
{statements_text}

以下のJSON形式で回答してください:
{{
  "winner": "user" | "ai" | "draw",
  "reasoning": "勝者を選んだ理由（2-3文）",
  "user_evaluation": "ユーザーの議論評価（1-2文）",
  "ai_evaluation": "AIの議論評価（1-2文）"
}}
"""
        
        fair_judge_prompt = """あなたは人間対AIのディベートバトルを審判する、完全に中立な第三者の審判です。

【重要な評価基準】
1. 論理性：主張に一貫性があり、根拠が明確か
2. 説得力：相手の意見に対して効果的に反論できているか  
3. 建設性：議論を前に進める発言ができているか
4. 誠実さ：相手の良い点を認めつつ、自分の立場を守れているか

【審判としての姿勢】
- AIが参加者であることによるバイアスを排除してください
- 人間の発言に対しても同じ基準で厳しく評価してください
- 特にAI側が一方的に論破している場合は、それが公平な議論だったか検討してください
- 僅差の場合は積極的にユーザーの勝利または引き分けを検討してください（AIは元々言語能力が高いため）
- 両者の発言回数や文字数の違いも考慮してください"""
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": fair_judge_prompt},
                {"role": "user", "content": judgment_prompt}
            ],
            temperature=0.5,
            max_tokens=500
        )
        
        # レスポンスを解析
        response_text = response.choices[0].message.content.strip()
        
        # JSON形式のテキストを抽出
        try:
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
                
                winner = result.get('winner', 'draw')
                reasoning = result.get('reasoning', '')
                user_eval = result.get('user_evaluation', '')
                ai_eval = result.get('ai_evaluation', '')
                
                judgment = f"【勝者】{winner.upper()}\n\n【審判コメント】{reasoning}\n\n【ユーザー評価】{user_eval}\n\n【AI評価】{ai_eval}"
                return winner, judgment
        except (json.JSONDecodeError, ValueError, KeyError):
            pass
        
        # JSON解析失敗時はテキスト全体を判定理由として使用
        winner = 'draw'
        judgment = response_text
        return winner, judgment
    
    except Exception as e:
        print(f"OpenAI API Error in judge_debate_ai: {str(e)}")
        # エラー時はデフォルト判定
        winner = 'draw'
        judgment = f"「{theme}」についてのディベート。AIが判定を生成できませんでしたが、両者の議論は同等です。"
        return winner, judgment


@csrf_exempt
@require_http_methods(["POST", "DELETE"])
def delete_debate(request, debate_id):
    """ディベートを削除"""
    try:
        debate = get_object_or_404(Debate, id=debate_id)
        debate.delete()
        return JsonResponse({'status': 'success', 'message': 'ディベートを削除しました'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def transcribe_audio(request):
    """音声ファイルをWhisper APIで文字起こしする"""
    try:
        if 'audio' not in request.FILES:
            return JsonResponse({'status': 'error', 'message': 'オーディオファイルが見つかりません'}, status=400)
        
        audio_file = request.FILES['audio']
        
        if not OPENAI_AVAILABLE:
            return JsonResponse({'status': 'error', 'message': 'OpenAIライブラリが利用できません'}, status=500)
        
        from django.conf import settings
        
        if not settings.OPENAI_API_KEY:
            return JsonResponse({'status': 'error', 'message': 'OpenAI APIキーが設定されていません'}, status=500)
        
        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            
            print(f"[Debate] Whisper API呼び出し中... ファイルサイズ: {audio_file.size} bytes")
            
            # DjangoのUploadedFileをバイナリデータに変換
            # ファイルポインタを最初に戻す
            audio_file.seek(0)
            audio_data = audio_file.read()
            
            print(f"[Debate] 読み込んだバイナリデータサイズ: {len(audio_data)} bytes")
            
            # BytesIOでラップしてOpenAI APIに渡す
            from io import BytesIO
            audio_buffer = BytesIO(audio_data)
            audio_buffer.name = audio_file.name
            
            # Whisper APIで文字起こし
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_buffer,
                language="ja",
                response_format="text"
            )
            
            text = transcript.strip()
            
            # 禁止文字をチェック（オプション）
            forbidden_words = [
                "ご視聴ありがとうございました",
                "最後までご視聴頂き有難うございました。",
                "字幕",
                "チャンネル登録",
            ]
            
            if any(word in text for word in forbidden_words):
                print(f"[Debate] 禁止文字を検知したため、この発言を破棄します")
                return JsonResponse({'status': 'success', 'text': ''})
            
            print(f"[Debate] Whisper API成功: {text}")
            
            return JsonResponse({'status': 'success', 'text': text})
        
        except Exception as e:
            print(f"[Debate] Whisper API error: {str(e)}")
            import traceback
            traceback.print_exc()
            return JsonResponse({'status': 'error', 'message': f'Whisper APIエラー: {str(e)}'}, status=500)
    
    except Exception as e:
        print(f"[Debate] transcribe_audio error: {str(e)}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def assign_positions_ai(theme, ai_type):
    """AIにテーマを与えて、ユーザーとAIの立場を割り振る"""
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key or not OPENAI_AVAILABLE:
        # フォールバック：ランダムに立場を割り振る
        positions = [
            ("賛成派", "反対派"),
            ("反対派", "賛成派"),
        ]
        return random.choice(positions)
    
    try:
        client = OpenAI(api_key=api_key)
        
        prompt = f"""
以下のテーマについて、ユーザーとAIの立場を決定してください。
テーマ: {theme}

AIのディベートスタイル: {ai_type}

指示:
1. テーマに対して、対立する2つの立場を提示してください
2. 以下の形式で回答してください:
   ユーザーの立場: [立場1 (20文字以内)]
   AIの立場: [立場2 (20文字以内)]

例:
テーマ: AIは人間の雇用を奪うべきか
ユーザーの立場: 雇用を奪う可能性がある
AIの立場: 新しい雇用機会も生まれる
"""
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "あなたはディベートの立場割り振り担当者です。バランスの取れた対立する2つの立場を提案します。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )
        
        # レスポンスを解析
        text = response.choices[0].message.content.strip()
        lines = text.split('\n')
        
        user_position = "未決定"
        ai_position = "未決定"
        
        for line in lines:
            if "ユーザーの立場" in line:
                user_position = line.split(":", 1)[-1].strip()
            elif "AIの立場" in line:
                ai_position = line.split(":", 1)[-1].strip()
        
        return user_position, ai_position
    
    except Exception as e:
        print(f"Position assignment error: {str(e)}")
        # フォールバック
        positions = [
            ("賛成派", "反対派"),
            ("反対派", "賛成派"),
        ]
        return random.choice(positions)