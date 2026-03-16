import os
import time
import json
import sys
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    TemplateSendMessage, ButtonsTemplate, MessageAction,
    QuickReply, QuickReplyButton
)
from google.api_core import exceptions
import google.generativeai as genai
import requests

# Diagnostics
try:
    import fastapi
    print(f"FastAPI version: {fastapi.__version__}")
except ImportError:
    print("FATAL: FastAPI is NOT installed.")

app = FastAPI()

# --- Shared Utilities ---

def get_jst_now():
    return datetime.now(timezone(timedelta(hours=9)))

CANCEL_LOG = {} # {user_id: timestamp_of_cancel}

def is_cancelled(uid):
    if uid in CANCEL_LOG:
        # Cancel within last 5 minutes
        if time.time() - CANCEL_LOG[uid] < 300:
            return True
    return False

class Notifier:
    def __init__(self):
        self.token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        self.owner_id = os.getenv("LINE_USER_ID")
        self.url = "https://api.line.me/v2/bot/message/push"

    def send_line_notification(self, text: str, target_id: Optional[str] = None):
        dest_id = target_id or self.owner_id
        if not self.token or not dest_id:
            return
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
        chunks = [text[i:i+4500] for i in range(0, len(text), 4500)]
        for chunk in chunks:
            payload = {"to": dest_id, "messages": [{"type": "text", "text": chunk}]}
            try:
                res = requests.post(self.url, headers=headers, json=payload)
                res.raise_for_status()
            except Exception as e:
                print(f"LINE failure: {e}")

# --- News AI Logic ---

class NewsResearcher:
    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=self.gemini_key)
        self.models_to_try = [
            "models/gemini-2.5-flash", "models/gemini-2.5-flash-lite", 
            "models/gemini-2.0-flash", "models/gemini-flash-latest",
            "models/gemini-1.5-flash", "models/gemini-flash-lite-latest",
            "models/gemini-pro-latest"
        ]

    def search_news(self, query: Optional[str] = None) -> List[Dict]:
        jst_now = get_jst_now()
        base_query = query if query else "latest AI technology trends and research 2024-2025"
        # Broaden search to recent trends (weekly/recent)
        search_query = f"latest AI tools models research releases this week {base_query} {jst_now.strftime('%Y-%m-%d')}"
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key, 
            "query": search_query, 
            "search_depth": "advanced", 
            "max_results": 10
        }
        res = requests.post(url, json=payload)
        res.raise_for_status()
        return res.json().get('results', [])

    def filter_and_extract_facts(self, search_results: List[Dict], query: Optional[str] = None) -> str:
        current_date_str = get_jst_now().strftime("%Y年%m月%d日")
        topic_label = f"「{query}」" if query else "全般"
        context = "\n\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in search_results])
        prompt = f"""
あなたは世界最先端のAI技術リサーチアナリストです。
ターゲット：{topic_label} に関するAI動向。

以下の検索結果から、直近（ここ1週間〜1ヶ月以内）の「最も技術的価値が高く、かつ最新の」情報を3つ厳選し、冷静に分析してください。

【厳守：情報の二重検証（ダブルチェック）】
1. **鮮度の照合**: 検索結果の日時を確認し、現在のトレンド（本日：{current_date_str}）と乖離がないか確認してください。古い情報は「最新」として扱わず、もし情報が古い場合はその旨を指摘するか、より新しい情報を優先してください。
2. **トピックの適合性**: 指示されたテーマ「{topic_label}」に合致しているか再確認してください。関係のないAIニュースはノイズとして排除してください。
3. **技術的ファクトの死守**: 実装、ベンチマーク、ライセンス、URLなどの「硬い情報」を優先してください。

「なんとなく」の要約は不要です。エンジニアに役立つ「生きたインテリジェンス」のみを出力してください。
"""
        for model_name in self.models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt).text
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg:
                    time.sleep(2)
                continue
        raise Exception(f"AIリサーチフェーズで失敗しました。最新の情報を取得できません。原因: {err_msg if 'err_msg' in locals() else '不明 (無料枠の制限 429 等)'}")

class NewsReporter:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.models_to_try = [
            "models/gemini-2.5-flash", "models/gemini-2.5-flash-lite",
            "models/gemini-2.0-flash", "models/gemini-1.5-flash",
            "models/gemini-flash-latest", "models/gemini-pro-latest"
        ]

    def generate_report(self, facts: str, query: Optional[str] = None) -> str:
        current_date = get_jst_now().strftime("%Y年%m月%d日")
        topic_label = f"【テーマ：{query}】" if query else "【AI全般リサーチ】"
        prompt = f"""
あなたはトップエンジニア向けの技術インテリジェンス・レポートを執筆するシニアアナリストです。
以下の分析データに基づき、「AI技術インテリジェンス・プロレポート」を作成してください。

【分析データ】
{facts}

【レポートの構成】
1. **AI技術インテリジェンス・プロレポート ({current_date})** {topic_label}
2. **キー・インサイト**: このテーマ/動向の核心。
3. **技術詳細・最新情報**: 厳選された要素の深掘り。
4. **実装・活用のヒント**: 最新のトレンドをどう武器にするか。
5. **リソース一覧**: GitHub / 公式ページ / Xアカウント等。

挨拶、装飾、一言感想などは一切不要。Markdown形式で提供してください。
"""
        for model_name in self.models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt).text
            except Exception as e:
                if "429" in str(e):
                    time.sleep(2)
                continue
        raise Exception("AIレポート生成に失敗しました。")

class TechConsultant:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.models_to_try = ["models/gemini-2.0-flash", "models/gemini-2.0-flash-exp", "models/gemini-1.5-flash"]

    def provide_advice(self, query: str) -> str:
        prompt = f"ITソリューションアーキテクトとして具体的な技術スタックや開発の第一歩をアドバイスしてください。\n\n【相談】\n{query}"
        for model_name in self.models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt).text
            except: continue
        raise Exception("技術相談に失敗しました。")

# --- Stock AI Logic ---

class StockAnalyzer:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        # Using 2.0 Flash Thinking for the requested config support
        self.model_name = "models/gemini-2.0-flash-thinking-exp-01-21"

    def analyze_stock(self, query: str) -> str:
        jst_now = get_jst_now()
        current_date = jst_now.strftime("%Y年%m月%d日")
        
        full_instruction = f"""
あなたはプロの機関投資家向け金融ストラテジストです。
Google Searchツールを使用して最新情報を取得し、以下の【絶対ルール】を遵守してレポートを作成してください。

【絶対ルール】
1. 事実の厳守: Google Searchで取得した最新データのみに基づいて分析・記述すること。
2. 捏造の禁止: 提供されていない経済指標、株価、ニュース、時期、事象をAI自身の知識から補完・推測して記述することを固く禁ずる。
3. 時間軸の同期: 現在の日付は {current_date} である。市場が閉まっている週末や祝日の場合は、直近の営業日のデータを最新として扱うこと。
4. 客観性: 感情的な表現や曖昧な推測を排除し、論理的かつ客観的な事実の因果関係のみを記述すること。
5. フォーマットの厳守: 指定された [出力構成] の見出し、テーブル、リスト形式を完全に再現すること。

---

### [出力構成]
# 【市場全体（マクロ概況）】 株式インテリジェンス・完全レポート ({current_date})

### エグゼクティブ・サマリー
（市場の現状、追い風、リスク要因を150字程度で論理的に要約）

### 5段階スコア・カード
（以下の項目を★1〜5で評価し、客観的な根拠を簡潔に記載するテーブルを出力）
| 評価項目 | スコア | 根拠の要約 |
|:---|:---|:---|
| 成長性 | | |
| 収益性 | | |
| 安全性 | | |
| 割安性 | | |
| 外部環境耐性 | | |

### 統合格付け (Rating)
## （S, A, B, C, Dのいずれか1文字）
**解説:**
（現在の市場に対するスタンスを客観的・論理的に解説）

### 業績・財務の深掘り
（マクロ経済指標や企業業績に関するニュースに基づき、現在の状態を分析）

### テクニカル・チャートの視点
（最新の株価データ、移動平均線、出来高などの事実に基づき、現状のトレンドを分析）

### マクロの波及インテリジェンス
（ニュースや金利・為替データを基に、事実の波及経路を論理的に記述。最大3つ）
1. **[要因のタイトル]**
   * **事象:** （データにある事実）
   * **波及経路:** （その事実が市場にどう波及するか）

### 競合比較・市場優位性
（グローバルと比較した際の、現在の日本市場の優位性と課題を箇条書きで記述）

### シナリオ予測とテールリスク
1. **ベースシナリオ（確率50%）：**
2. **アップサイドシナリオ（確率25%）：**
3. **ダウンサイドシナリオ（確率25%）：**
**テールリスク：** （想定外のサプライズ要因）

### 戦術的スクリーニング
（恩恵を受ける論理的根拠のあるテーマと代表的なセクターまたは銘柄を3つ）

---

リサーチおよび分析対象：{query}
"""
        # Mapping correct tool syntaxes to models to avoid quota exhaustion from blind retries
        # Mapping correct tool syntaxes to models
        configs_to_try = [
            {"m": "models/gemini-2.5-flash", "t": "google_search", "think": False},
            {"m": "models/gemini-2.5-flash-lite", "t": "google_search", "think": False},
            {"m": "models/gemini-2.5-flash", "t": "google_search_retrieval", "think": False},
            {"m": "models/gemini-2.0-flash", "t": "google_search", "think": False},
            {"m": "models/gemini-2.0-flash", "t": "google_search_retrieval", "think": False},
            {"m": "models/gemini-pro-latest", "t": "google_search_retrieval", "think": False},
            {"m": "models/gemini-1.5-flash", "t": "google_search_retrieval", "think": False},
            {"m": "models/gemini-flash-latest", "t": "google_search_retrieval", "think": False}
        ]
        
        last_error = "初期化失敗"
        for cfg in configs_to_try:
            try:
                # Some models/SDK versions prefer dict, some Tool objects. 
                # Given legacy SDK, we try the most compatible dict format first.
                model = genai.GenerativeModel(
                    model_name=cfg["m"],
                    tools=[{cfg["t"]: {}}]
                )
                gen_config = {}
                if cfg.get("think"):
                    gen_config["thinking_config"] = {"include_thoughts": True}
                
                response = model.generate_content(full_instruction, generation_config=gen_config)
                return response.text
            except Exception as e:
                err_msg = str(e)
                last_error = f"{cfg['m']} ({cfg['t']}): {err_msg}"
                print(f"Trial failed: {last_error}")
                if "429" in err_msg:
                    time.sleep(3) # Aggressive wait for stock as it's more likely to hit limits
                continue
        
        # Final attempt without any tools if all else fails
        fallback_models = ["models/gemini-2.0-flash", "models/gemini-pro-latest", "models/gemini-flash-latest"]
        
        # When falling back, we need to relax the strict "No Fabrication/Search Only" rules
        # to allow the AI to provide a general report based on its base knowledge.
        relaxed_instruction = full_instruction.replace(
            "Google Searchツールを使用して最新情報を取得し、以下の【絶対ルール】を遵守してレポートを作成してください。",
            "Google Searchが一時的に利用できないため、あなたの知識に基づき、可能な限り正確で論理的な分析レポートを作成してください（最新でない可能性があることを踏まえた一般的な動向でも構いません）。"
        ).replace(
            "1. 事実の厳守: Google Searchで取得した最新データのみに基づいて分析・記述すること。",
            "1. 事実の尊重: 可能な限り事実に基づき、推測である場合はその旨を明示すること。"
        ).replace(
            "2. 捏造の禁止: 提供されていない経済指標... AI自身の知識から補完・推測して記述することを固く禁ずる。",
            "2. 論理的推論: 最新データが不足している場合は、あなたの知識に基づいた論理的な市場分析を提供してください。"
        )

        for fm in fallback_models:
            try:
                model = genai.GenerativeModel(fm)
                response = model.generate_content(relaxed_instruction)
                return response.text + "\n\n(注意: Google Searchがクォータ制限のため、AIの知識(カットオフ時点)に基づき回答しました。最新情報は含まれていない可能性があります。)"
            except:
                continue
        
        raise Exception(f"全構成で失敗しました。最新エラー: {last_error}\n(無料枠の制限 429 等により、全てのAIモデルが応答できませんでした)")

class InvestmentConsultant:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.models_to_try = ["models/gemini-2.0-flash", "models/gemini-2.0-flash-exp", "models/gemini-1.5-flash"]

    def provide_advice(self, query: str) -> str:
        prompt = f"ファイナンシャル・アドバイザーとして投資のアドバイスをしてください。推奨セクターや指標、リスク管理を多角的に答えてください。\n\n【相談】\n{query}"
        for model_name in self.models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt).text
            except: continue
        raise Exception("投資相談に失敗しました。")

# --- Orchestration ---

def run_news_flow(target_id: str, query: Optional[str] = None):
    notifier = Notifier()
    try:
        researcher = NewsResearcher()
        reporter = NewsReporter()
        results = researcher.search_news(query)
        facts = researcher.filter_and_extract_facts(results, query)
        report = reporter.generate_report(facts, query)
        if is_cancelled(target_id): return
        notifier.send_line_notification(report, target_id)
    except Exception as e:
        if not is_cancelled(target_id):
            notifier.send_line_notification(f"AIリサーチ失敗: {str(e)}", target_id)

def run_news_consultation(query: str, target_id: str):
    notifier = Notifier()
    try:
        consultant = TechConsultant()
        advice = consultant.provide_advice(query)
        if is_cancelled(target_id): return
        notifier.send_line_notification(advice, target_id)
    except Exception as e:
        if not is_cancelled(target_id):
            notifier.send_line_notification(f"技術相談失敗: {str(e)}", target_id)

def run_stock_flow(query: str, target_id: str):
    notifier = Notifier()
    try:
        analyzer = StockAnalyzer()
        report = analyzer.analyze_stock(query)
        if is_cancelled(target_id): return
        notifier.send_line_notification(report, target_id)
    except Exception as e:
        if not is_cancelled(target_id):
            notifier.send_line_notification(f"株分析失敗: {str(e)}", target_id)

def run_stock_consultation(query: str, target_id: str):
    notifier = Notifier()
    try:
        consultant = InvestmentConsultant()
        advice = consultant.provide_advice(query)
        if is_cancelled(target_id): return
        notifier.send_line_notification(advice, target_id)
    except Exception as e:
        if not is_cancelled(target_id):
            notifier.send_line_notification(f"投資相談失敗: {str(e)}", target_id)

# --- Webhook Handlers ---

channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(channel_access_token or "dummy")
line_handler = WebhookHandler(channel_secret or "dummy")

@app.post("/api/webhook")
@app.post("/api/index")
async def news_webhook(request: Request, background_tasks: BackgroundTasks):
    signature = request.headers.get("X-Line-Signature")
    body = (await request.body()).decode("utf-8")
    
    @line_handler.add(MessageEvent, message=TextMessage)
    def handle_news(event):
        msg = event.message.text.strip()
        uid = event.source.user_id
        
        # Check for specific instruction: "Something about Something"
        summary_match = re.search(r"(.+)(について|についてまとめて|を調べて|をリサーチ)", msg)
        
        if any(k in msg for k in ["キャンセル", "中止", "やめて"]):
            CANCEL_LOG[uid] = time.time()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="リサーチを中断（非表示）しました。"))
        elif any(k in msg for k in ["作りたい", "おすすめ", "技術", "相談"]):
            if uid in CANCEL_LOG: del CANCEL_LOG[uid]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="検討を開始します…"))
            background_tasks.add_task(run_news_consultation, msg, uid)
        elif summary_match or any(k in msg for k in ["ニュース", "リサーチ", "教えて"]):
            if uid in CANCEL_LOG: del CANCEL_LOG[uid]
            query = summary_match.group(1).strip() if summary_match else None
            display_theme = query if query else "最新AIニュース"
            
            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(text=f"「{display_theme}」を二重検証（ダブルチェック）してリサーチします！少々お待ちください。🤖")
            )
            background_tasks.add_task(run_news_flow, uid, query)
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="AIニュースや具体的なテーマの調査依頼をどうぞ！例：「画像生成AIについてまとめて」"))

    try:
        line_handler.handle(body, signature)
    except: pass
    return "OK"

@app.post("/api/stock")
async def stock_webhook(request: Request, background_tasks: BackgroundTasks):
    signature = request.headers.get("X-Line-Signature")
    body = (await request.body()).decode("utf-8")
    
    @line_handler.add(MessageEvent, message=TextMessage)
    def handle_stock(event):
        msg = event.message.text.strip()
        uid = event.source.user_id
        
        if any(k in msg for k in ["キャンセル", "中止", "やめて"]):
            CANCEL_LOG[uid] = time.time()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="分析結果の送信をキャンセルします。"))
            return

        is_stock_code = msg.isdigit() and len(msg) == 4
        general_keywords = ["レポートお願い", "ニュース教えて", "概況", "最新情報", "市場の状況"]
        is_general_request = any(k in msg for k in general_keywords) or msg == "レポート"
        
        if is_stock_code or is_general_request:
            if uid in CANCEL_LOG: del CANCEL_LOG[uid]
            if is_general_request:
                target_name = "市場全体（マクロ概況）"
                display_name = "マクロ概況と注目銘柄"
            else:
                target_name = f"銘柄コード {msg}"
                display_name = f"銘柄コード {msg}"

            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(
                    text=f"「{display_name}」について、高精度なプロ用レポートを作成します！少々お待ちください📈",
                    quick_reply=QuickReply(items=[
                        QuickReplyButton(action=MessageAction(label="途中でキャンセル", text="キャンセル")),
                        QuickReplyButton(action=MessageAction(label="市場の概況レポート", text="レポートお願い"))
                    ])
                )
            )
            background_tasks.add_task(run_stock_flow, target_name, uid)
            
        elif any(k in msg for k in ["相談", "投資", "買い", "売り"]):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="投資アドバイスを用意します。"))
            background_tasks.add_task(run_stock_consultation, msg, uid)
        else:
            buttons_template = ButtonsTemplate(
                title='株式投資・市場分析AI',
                text='4桁のコードを入力するか、ボタンを選択してください。',
                actions=[
                    MessageAction(label='市場の概況レポート', text='レポートお願い'),
                    MessageAction(label='投資戦略の相談', text='投資相談に乗って'),
                ]
            )
            line_bot_api.reply_message(
                event.reply_token,
                TemplateSendMessage(alt_text='メニューを選択してください', template=buttons_template)
            )

    try:
        line_handler.handle(body, signature)
    except: pass
    return "OK"

@app.get("/")
async def health():
    return {"status": "Universal AI Bot v11 (Live Multi-Check) is running.", "server_time": str(datetime.now())}

@app.get("/cron")
@app.get("/api/index/cron")
async def news_cron(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_news_flow, os.getenv("LINE_USER_ID"))
    return "OK"
