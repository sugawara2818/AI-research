import os
import time
import json
import sys
import re
from datetime import datetime
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
        self.models_to_try = ["models/gemini-2.5-flash", "models/gemini-2.0-flash-exp", "models/gemini-1.5-flash"]

    def search_news(self, query: str = "latest AI technology trends and research 2024-2025") -> List[Dict]:
        # Broaden search to recent trends (weekly/recent) instead of strictly 'today'
        search_query = f"latest AI tools models research releases this week {query}"
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

    def filter_and_extract_facts(self, search_results: List[Dict]) -> str:
        current_date_str = datetime.now().strftime("%Y年%m月%d日")
        context = "\n\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in search_results])
        prompt = f"""
あなたは世界最先端のAI技術リサーチアナリストです。
以下の検索結果から、直近（ここ1週間〜1ヶ月以内）で「最も技術的価値が高く、かつ最新の」AI動向を3つ厳選し、冷静に分析してください。

【リサーチ基準】
1. **鮮度の確認**: 検索結果が古すぎないか（数ヶ月以上前でないか）確認してください。直近の発表や、最近注目されている出来事を優先してください。
2. **技術的ファクトの重視**: 実装方法、パラメータ数、ベンチマーク結果、ライセンス体系などの「硬い情報」を優先してください。
3. **リソースの特定**: 関連するGitHubリポジトリ、Hugging Faceモデル、公式論文、開発者のXアカウントを特定してください。

「なんとなく凄そう」なものではなく、エンジニアが活用できる「生きた情報」のみを出力してください。
"""
        for model_name in self.models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt).text
            except: continue
        raise Exception(f"AIリサーチフェーズで失敗しました。最新の情報を取得できません。")

class NewsReporter:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

    def generate_report(self, facts: str) -> str:
        current_date = datetime.now().strftime("%Y年%m月%d日")
        prompt = f"""
あなたはトップエンジニア向けの技術インテリジェンス・レポートを執筆するシニアアナリストです。
以下の分析データに基づき、「AI技術インテリジェンス・プロレポート」を作成してください。

【分析データ】
{facts}

【レポートの構成】
1. **AI技術インテリジェンス・プロレポート ({current_date})**
2. **キー・インサイト**: 今日の最重要動向とその背景。
3. **技術詳細・最新リリース**: 厳選された3つのトピックの深掘り。
4. **実装・活用のヒント**: エンジニアがどう向き合うべきか。
5. **リソース一覧**: GitHub / 公式ページ / Xアカウント等。

挨拶、装飾、一言感想などは「一切不要」です。プロフェッショナルで論理的なMarkdown形式で、高密度な情報を提供してください。
"""
        return self.model.generate_content(prompt).text

class TechConsultant:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

    def provide_advice(self, query: str) -> str:
        prompt = f"ITソリューションアーキテクトとして具体的な技術スタックや開発の第一歩をアドバイスしてください。\n\n【相談】\n{query}"
        return self.model.generate_content(prompt).text

# --- Stock AI Logic ---

class StockResearcher:
    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=self.gemini_key)
        self.models_to_try = ["models/gemini-2.5-flash", "models/gemini-2.0-flash-exp", "models/gemini-1.5-flash"]

    def search_stock_news(self, query: str) -> List[Dict]:
        current_date_str = datetime.now().strftime("%Y-%m-%d")
        print(f"Searching stock info for: {query} (Today: {current_date_str})")
        
        processed_query = query
        if "銘柄コード" in query:
            code = query.replace("銘柄コード", "").strip()
            processed_query = f"{code}.T {code} 証券コード"

        # Explicitly include the current date in the query to force fresh results
        search_query = (
            f"本日 {current_date_str} の {processed_query} 株価 日経平均 リアルタイム 決算短信 業績推移 "
            f"latest {current_date_str} {processed_query} stock price nikkei 225 index realtime financial update"
        )
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": search_query,
            "search_depth": "advanced",
            "max_results": 15
        }
        res = requests.post(url, json=payload)
        res.raise_for_status()
        return res.json().get('results', [])

    def extract_stock_insights(self, search_results: List[Dict], query: str) -> str:
        current_date_str = datetime.now().strftime("%Y年%m月%d日")
        context = "\n\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in search_results])
        prompt = f"""
あなたは「情報の鮮度」を命として動く、超精密なリサーチアナリストです。
ターゲット銘柄「{query}」について、以下の最新データをもとに「情報の二重検証（ダブルチェック）」を徹底した分析を行なってください。

【本日：{current_date_str}】

【厳守事項：データの鮮度ダブルチェック】
1. **日付の検証**: 各検索結果のデータが「いつ」のものか必ず確認してください。本日（{current_date_str}）の日経平均や株価データと矛盾がないか照合し、古いデータ（数日・数週間前のもの）を「最新」として扱わないよう二重にチェックしてください。
2. **情報の整合性**: 日経平均が現在急落/急騰している場合、その背景が本日の事象と合致しているか確認してください。ハルシネーション（情報の捏造）は許されません。
3. **最新ファクトの優先**: 決算直後の場合、昨日の予想ではなく「本日の着地数値」を死守して抽出してください。

【分析の深化項目】
- **財務・指標**: 直近の数値推移と、本日時点でのPER/PBR等の正確な算出。
- **市場・世界情勢の連動**: 今、この瞬間に動いている材料（為替、金利、地政学リスク）がどう銘柄にヒットしているか。
- **需給・テクニカル**: 本日の出来高、出来高変化、昨晩のPTS動向など。

挨拶は不要です。今日という日付に100%立脚した、純度の高いインテリジェンスのみを出力してください。
"""
        for model_name in self.models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt).text
            except: continue
        raise Exception(f"分析フェーズで失敗しました。本日({current_date_str})の情報の取得に問題があります。")

class StockReporter:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

    def generate_stock_report(self, insights: str, query: str) -> str:
        current_date = datetime.now().strftime("%Y年%m月%d日")
        prompt = f"""
あなたは機関投資家が「最終判断の根拠」とする、最高峰の株式インテリジェンス・レポートを執筆するアナリストです。
以下の分析データに基づき、銘柄「{query}」の「株式インテリジェンス・完全レポート」を完成させてください。

【分析データ】
{insights}

【レポートの構成（高密度・多層的）】
1. **【{query}】 株式インテリジェンス・完全レポート ({current_date})**
2. **エグゼクティブ・サマリー**: 今、この銘柄で起きていることの核心を3本指の箇条書きで。
3. **5段階スコア・カード**: 成長性/収益性/安全性/割安性/外部環境耐性（★1〜5）を表形式で。
4. **統合格付け (Rating)**: S / A / B / C / D / E を大きく表示（解説付き）。
5. **業績・財務の深掘り**: 数値に基づく直近の評価と、将来の期待値。
6. **テクニカル・チャートの視点**: 需給バランスと、投資家が意識すべき価格帯。
7. **マクロの波及インテリジェンス**: 世界情勢がこの銘柄のPL/BSにヒットする経路（イラン情勢、米利下げ等、今現在最も重要な要因を取り上げること）。
8. **競合比較・市場優位性**: ライバルとの対比で見えた「この企業だけの強み」。
9. **シナリオ予測とテールリスク**: 市場がまだ織り込んでいない、想定外のサプライズ要因。
10. **戦術的スクリーニング**: 同セクター等の注目関連銘柄（3選）。

Markdown形式で、論理的かつ洗練された構成にしてください。挨拶や最後の一言アドバイスは「一切不要」です。
"""
        return self.model.generate_content(prompt).text

class InvestmentConsultant:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

    def provide_advice(self, query: str) -> str:
        prompt = f"ファイナンシャル・アドバイザーとして投資のアドバイスをしてください。推奨セクターや指標、リスク管理を多角的に答えてください。\n\n【相談】\n{query}"
        return self.model.generate_content(prompt).text

# --- Orchestration ---

def run_news_flow(target_id: str, query: Optional[str] = None):
    notifier = Notifier()
    try:
        researcher = NewsResearcher()
        reporter = NewsReporter()
        results = researcher.search_news(query) if query else researcher.search_news()
        facts = researcher.filter_and_extract_facts(results)
        report = reporter.generate_report(facts)
        if is_cancelled(target_id): return
        notifier.send_line_notification(report, target_id)
    except Exception as e:
        if not is_cancelled(target_id):
            notifier.send_line_notification(f"ニュースリサーチ失敗: {str(e)}", target_id)

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
        researcher = StockResearcher()
        reporter = StockReporter()
        results = researcher.search_stock_news(query)
        insights = researcher.extract_stock_insights(results, query)
        report = reporter.generate_stock_report(insights, query)
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
        msg = event.message.text
        uid = event.source.user_id
        if any(k in msg for k in ["キャンセル", "中止", "やめて"]):
            CANCEL_LOG[uid] = time.time()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="リサーチを中断（非表示）しました。"))
        elif any(k in msg for k in ["作りたい", "おすすめ", "技術", "相談"]):
            if uid in CANCEL_LOG: del CANCEL_LOG[uid]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="検討を開始します…"))
            background_tasks.add_task(run_news_consultation, msg, uid)
        elif any(k in msg for k in ["ニュース", "リサーチ", "教えて"]):
            if uid in CANCEL_LOG: del CANCEL_LOG[uid]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="AIニュースをリサーチします！"))
            background_tasks.add_task(run_news_flow, uid)
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="AIニュースや開発の相談をどうぞ！"))

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
    return {"status": "Universal AI Bot v10 (Precision Mode) is running."}

@app.get("/cron")
@app.get("/api/index/cron")
async def news_cron(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_news_flow, os.getenv("LINE_USER_ID"))
    return "OK"
