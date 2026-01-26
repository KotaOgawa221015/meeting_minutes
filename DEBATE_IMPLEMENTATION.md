# ディベート機能実装ガイド

## 概要

議事録システムに加えて、**AIディベートシステム** が実装されました。ユーザーがAIとリアルタイムでディベートを行い、最後にAIが勝敗を判定します。

## 機能説明

### 1. ディベートの流れ

```
1. ディベートの作成 (Create)
   ├─ テーマを入力
   └─ AIのタイプを選択（論理的、創造的、外交的、攻撃的）

2. 先攻後攻の自動決定
   ├─ ユーザーが先攻の場合
   │  └─ ユーザーが最初に意見を述べる
   └─ AIが先攻の場合
      └─ AIが最初に意見を生成する

3. ディベートの展開 (Room)
   ├─ ユーザーが意見を入力・送信
   └─ AIが自動で応答を生成

4. ディベート終了 & 判定 (Detail)
   ├─ ユーザーが「ディベート終了」を選択
   ├─ AIが全発言を分析して勝敗を判定
   └─ 結果と詳細な判定理由を表示
```

### 2. 画面構成

#### 2.1 ディベート一覧 (debate/index.html)
- **背景色**: オレンジ系 `rgb(255, 140, 80)` 
- **議事録システムとの対比**: 議事録の青紫色に対するコンプリメンタリーカラー
- **機能**:
  - 作成されたディベートの一覧表示
  - ステータス表示（セットアップ、ディベート中、完了）
  - 勝者表示（ユーザー、AI、引き分け）
  - ディベートの削除機能

#### 2.2 ディベート作成 (debate/create.html)
- **入力項目**:
  - テーマ（必須）
  - AIタイプ選択（プルダウンメニュー）
    - 🧠 論理的 - 理屈で攻める
    - 💡 創造的 - 新しい視点を提示
    - 🤝 外交的 - 相手の意見を尊重
    - ⚡ 攻撃的 - 相手の弱点を突く

#### 2.3 ディベートルーム (debate/room.html)
- **左パネル**: セットアップ情報
- **右パネル**: ディベート実施エリア
  - テーマとAIタイプの表示
  - ユーザーとAIの発言をリアルタイム表示
  - ユーザー入力フォーム

#### 2.4 ディベート詳細 (debate/detail.html)
- **結果表示**:
  - 勝者情報
  - AIの判定理由
  - 全発言の履歴
- **操作**:
  - ディベート一覧への戻却
  - ディベート再開（未完了の場合）
  - ディベート削除

### 3. 議事録システムとの連携

議事録システムの `index.html` に以下のボタンが追加されました：

```html
<a href="{% url 'debate_index' %}" class="btn btn-debate">🎤 ディベートシステム</a>
```

これにより、議事録一覧ページからワンクリックでディベートシステムにアクセスできます。

## データベースモデル

### Debate モデル
```python
class Debate(models.Model):
    title              # ディベートのテーマ
    created_at         # 作成日時
    created_by         # 作成者（ユーザー）
    ai_type            # AIのタイプ（logical, creative, diplomatic, aggressive）
    status             # ステータス（setup, debating, completed）
    first_speaker      # 先攻（user or ai）- 自動決定
    winner             # 勝者（user, ai, draw）
    judgment_text      # AIの判定理由
```

### DebateStatement モデル
```python
class DebateStatement(models.Model):
    debate             # 関連するディベート
    speaker            # 発言者（user or ai）
    text               # 発言内容
    order              # 発言順序
    created_at         # 作成日時
```

## API エンドポイント

### ディベート管理
- `GET /minutes/debate/` → ディベート一覧表示
- `POST /minutes/debate/create/` → ディベート作成
- `GET /minutes/debate/<id>/` → ディベートルーム
- `GET /minutes/debate/<id>/detail/` → ディベート詳細
- `DELETE /minutes/debate/<id>/delete/` → ディベート削除

### ディベート操作
- `POST /minutes/debate/<id>/statement/add/` → 発言を保存
- `POST /minutes/debate/<id>/ai-response/` → AIの応答を生成
- `POST /minutes/debate/<id>/judge/` → ディベートを判定

## 実装の詳細

### 1. AIの応答生成 (`generate_ai_argument()`)
現在の実装は簡易版で、AIタイプに基づいたテンプレート応答を返しています。

**実装例**:
```python
def generate_ai_argument(theme, user_statement, ai_type):
    arguments = {
        'logical': f"ご意見ありがとうございます。「{theme}」についてですが、論理的に考えると...",
        'creative': f"興味深いご指摘です。「{theme}」を創造的に捉えると...",
        'diplomatic': f"確かなご意見ですね。「{theme}」という点で...",
        'aggressive': f"ご指摘ありがとうございます。しかし「{theme}」について...",
    }
    return arguments.get(ai_type, arguments['logical'])
```

**改善案**: 外部のLLMAPI（OpenAI, Anthropic等）と統合して、より自然で高度な応答を生成できます。

### 2. ディベート判定 (`judge_debate_ai()`)
現在の実装は簡易版で、発言中のキーワード出現数でスコアを計算しています。

**実装例**:
```python
def judge_debate_ai(theme, ai_type, statements):
    user_score = 0
    ai_score = 0
    
    for stmt in statements:
        if stmt['speaker'] == 'user':
            if any(word in stmt['text'] for word in ['理由', '根拠', '証拠', 'なぜなら']):
                user_score += 1
    
    # スコアに基づいて勝者を決定
    if user_score > ai_score:
        winner = 'user'
    elif ai_score > user_score:
        winner = 'ai'
    else:
        winner = 'draw'
    
    return winner, judgment
```

**改善案**: LLMを使用してセンチメント分析や論理的な説得力を詳細に評価できます。

## 使用技術

- **バックエンド**: Django 5.0
- **フロントエンド**: HTML5, CSS3, Vanilla JavaScript
- **データベース**: SQLite（開発環境）
- **スタイル**: レスポンシブデザイン（モバイル対応）

## ファイル構造

```
minutes/
├── models.py          # Debate, DebateStatement モデル追加
├── views.py           # ディベート関連ビュー追加
├── urls.py            # ディベートURLルーティング追加
└── migrations/
    └── 0008_debate_debatestatement.py  # マイグレーション

templates/debate/
├── index.html         # ディベート一覧
├── create.html        # ディベート作成
├── room.html          # ディベートルーム（本機能）
└── detail.html        # ディベート詳細

templates/minutes/
└── index.html         # 議事録一覧（ディベート用リンク追加）
```

## 今後の拡張案

1. **実際のLLM統合**
   - OpenAI API (GPT-4) を使用した高度な応答生成
   - 複数のLLMプロバイダーのサポート

2. **音声入力対応**
   - Web Speech API を使用したマイク入力
   - 発言の自動文字起こし

3. **ディベート分析**
   - 論理的一貫性の分析
   - 相手の主張への反論の有効性評価
   - ディベートのヒートマップ表示

4. **マルチプレイヤー対応**
   - 複数のユーザーとAIによる集団ディベート
   - ユーザー同士のディベート

5. **実績追跡**
   - ユーザーの勝率統計
   - 得意なテーマ・AIタイプの分析
   - ランキングシステム

6. **カスタマイズ機能**
   - AIの性格や話し方をカスタマイズ
   - ディベート時間制限の設定
   - 評価基準のカスタマイズ

## トラブルシューティング

### マイグレーション エラー
```bash
# マイグレーション作成
python manage.py makemigrations

# マイグレーション適用
python manage.py migrate
```

### テンプレートが見つからない
- テンプレートパスが正しいか確認: `templates/debate/*.html`
- Django設定でテンプレートディレクトリが正しく設定されているか確認

### JavaScriptエラー
- ブラウザの開発者ツール（F12）でコンソール確認
- CSRF トークンが正しく送信されているか確認

## ライセンス

このプロジェクトのディベート機能は、議事録システムと同じライセンスの下で配布されています。

---

**作成日**: 2026年1月26日  
**最終更新**: 2026年1月26日
