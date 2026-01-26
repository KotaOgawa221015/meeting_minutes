from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json
import random
import os
from .models import Debate, DebateStatement

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


def debate_index(request):
    """ディベート一覧"""
    debates = Debate.objects.all()
    return render(request, 'debate/index.html', {'debates': debates})


def debate_create(request):
    """新しいディベートを作成"""
    if request.method == 'POST':
        title = request.POST.get('title', 'テーマなし')
        ai_type = request.POST.get('ai_type', 'logical')
        
        # 先攻後攻を自動決定（50%の確率）
        first_speaker = random.choice(['user', 'ai'])
        
        debate = Debate.objects.create(
            title=title,
            ai_type=ai_type,
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
    statements = debate.statements.all()
    
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
        ai_type = debate.ai_type
        
        # AIレスポンスを生成（OpenAI API を使用）
        ai_response = generate_ai_argument(theme, user_statement, ai_type)
        
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


def generate_ai_argument(theme, user_statement, ai_type):
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
        
        # AIタイプに応じたシステムプロンプトを作成
        system_prompts = {
            'logical': "あなたは論理的で理屈っぽいディベーター です。相手の意見に対して、論理的な矛盾点を指摘し、データや事例をもとに反論してください。",
            'creative': "あなたは創造的で新しい視点を提供するディベーター です。相手の意見に対して、従来の考え方にとらわれない新しい可能性や視点を提示してください。",
            'diplomatic': "あなたは相手の意見を尊重しながら、丁寧に異なる見方を提示するディベーター です。相手の意見の良い点を認めながらも、別の立場からの見方を述べてください。",
            'aggressive': "あなたは相手の弱点を突く攻撃的なディベーター です。相手の意見の不正確さ、根拠の不足、矛盾点を鋭く指摘してください。",
        }
        
        system_prompt = system_prompts.get(ai_type, system_prompts['logical'])
        
        # ユーザーの発言がない場合（最初のターン）
        if not user_statement:
            user_message = f"テーマ: {theme}\n\nこのテーマについて、あなたの最初の意見を述べてください。"
        else:
            user_message = f"テーマ: {theme}\n\n相手の意見: {user_statement}\n\nこの意見に対して、あなたの反論や異なる見方を述べてください。"
        
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
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "あなたは客観的で公平なディベート審判です。両者の議論の質、論理性、説得力を総合的に評価して勝敗を判定してください。"},
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
