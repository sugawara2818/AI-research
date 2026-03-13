import os
import time
import json
import sys
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
        url = "https://api.tavily.com/search"
        payload = {"api_key": self.tavily_key, "query": query, "search_depth": "advanced", "max_results": 5}
        res = requests.post(url, json=payload)
        res.raise_for_status()
        return res.json().get('results', [])

    def filter_and_extract_facts(self, search_results: List[Dict]) -> str:
        context = "\n\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in search_results])
        prompt = f"あなたは高度なAI技術アナリストです。以下の結果から開発者に価値ある動向を3つ厳選し、ツールリンクやXアカウントを含めて整理してください。\n\n【結果】\n{context}"
        for model_name in self.models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt).text
            except: continue
        raise Exception("News extraction failed.")

class NewsReporter:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

    def generate_report(self, facts: str) -> str:
        current_date = datetime.now().strftime("%Y年%m月%d日")
        prompt = f"ITエンジニア向けの「週刊AI技術サマリー({current_date})」を、事実に基づき論理的に作成してください。ツールやXアカウントをリソースとしてまとめてください。\n\n【事実】\n{facts}"
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
        print(f"Searching stock info for: {query}")
        # Balanced search query: Financials + Technicals + Macro/Geopolitics
        search_query = (
            f"{query} 株価 決算 業績見通し 財務分析 チャート動向 市場ニュース 世界情勢 "
            f"stock price earnings financial analysis chart trends market news global macro"
        )
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

    def extract_stock_insights(self, search_results: List[Dict], query: str) -> str:
        context = "\n\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in search_results])
        prompt = f"""
あなたは超一流のマルチアセット・アナリストです。銘柄「{query}」に関するあらゆる情報を精査し、投資判断に「真に必要な情報」を冷徹に選別して分析してください。

【検索結果】
{context}

【分析の鉄則】
1. **情報の取捨選択と重み付け**: 決算数値、成長戦略、需給動向、そして世界情勢。これらの中から、今この瞬間に最も市場が反応している要素（例：もし中東情勢が原油高を通じ業績に直結するなら重点的に、そうでなければ客観的事実として）を適切に選別してください。
2. **多角的なファクトチェック**: 単なるニュースの引き写しではなく、財務諸表の裏付け、指標（PER/PBR/ROE等）の妥当性、市場環境の変化をクロスチェックしてください。
3. **網羅性と死角の排除**: 重要なリスクを見落としていないか自問自答してください。マクロ経済の動向が個別株の前提を壊す場合は必ず言及し、逆に個別株の強みが市場を上回る場合も説明してください。
4. **定量的根拠の提示**: 5段階スコアリング（成長性、収益性、安全性、割安性、外部環境耐性）のための具体的数値を必ず抽出してください。

挨拶や装飾は不要です。高密度なインテリジェンスのみを出力してください。
"""
        for model_name in self.models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt).text
            except: continue
        raise Exception("Stock分析フェーズで、情報抽出に失敗しました。")

class StockReporter:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

    def generate_stock_report(self, insights: str, query: str) -> str:
        current_date = datetime.now().strftime("%Y年%m月%d日")
        prompt = f"""
あなたは機関投資家向けのトップストラテジストです。
以下の分析データに基づき、銘柄「{query}」の「戦略インテリジェンス・レポート」を作成してください。

【分析データ】
{insights}

【レポートの構成・必須要件】
1. **タイトル**: 戦略インテリジェンス・レポート ({current_date}): {query}
2. **エグゼクティブ・サマリー**: 現状の核心（3行以内）。
3. **5段階評価（スコアリング）**: 
   以下の5項目を5点満点（★）で評価し、表形式で出力してください。
   - 成長性 / 収益性 / 安全性 / 割安性 / 外部環境耐性
4. **総合評価 (A~E)**: 
   S(例外) / A(買い) / B(保留) / C(注視) / D(警戒) / E(売り) の中から一つ選び、大きく表示。
5. **詳細分析**: 世界情勢と業績の相関。
6. **戦術的スクリーニング**: 今日のデータから導き出される注目関連銘柄（3選）。
7. **一言（パンチライン）**: 最後に、投資家への魂の一言を添えてください。

Markdown形式で出力してください。
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
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="了解しました、現在のリサーチを中断（非表示）します。"))
        elif any(k in msg for k in ["作りたい", "おすすめ", "技術", "相談"]):
            if uid in CANCEL_LOG: del CANCEL_LOG[uid]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="技術的なご相談ですね。検討します…"))
            background_tasks.add_task(run_news_consultation, msg, uid)
        elif any(k in msg for k in ["ニュース", "リサーチ", "教えて"]):
            if uid in CANCEL_LOG: del CANCEL_LOG[uid]
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="AIニュースをリサーチして報告します！"))
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
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="了解です、分析結果の送信をキャンセルします。"))
            return

        is_stock_code = msg.isdigit() and len(msg) == 4
        general_keywords = ["レポートお願い", "ニュース教えて", "概況", "最新情報", "市場の状況"]
        is_general_request = any(k in msg for k in general_keywords) or msg == "レポート"
        
        if is_stock_code or is_general_request:
            if uid in CANCEL_LOG: del CANCEL_LOG[uid]
            if is_general_request:
                target_name = "市場全体（マクロ概況）"
                display_name = "市場全体の主要トピック"
            else:
                target_name = f"銘柄コード {msg}"
                display_name = f"銘柄コード {msg}"

            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(
                    text=f"「{display_name}」を分析します！少々お待ちください…📈",
                    quick_reply=QuickReply(items=[
                        QuickReplyButton(action=MessageAction(label="途中でキャンセル", text="キャンセル")),
                        QuickReplyButton(action=MessageAction(label="市場の概況レポート", text="レポートお願い"))
                    ])
                )
            )
            background_tasks.add_task(run_stock_flow, target_name, uid)
            
        elif any(k in msg for k in ["相談", "投資", "買い", "売り"]):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="投資戦略のアドバイスを用意します。"))
            background_tasks.add_task(run_stock_consultation, msg, uid)
        else:
            buttons_template = ButtonsTemplate(
                title='株式投資・市場分析AI',
                text='4桁のコードを入力するか、ボタンからレポートをリクエストできます。',
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
    return {"status": "Universal AI Bot v5 (Scoring Mode) is running."}

@app.get("/cron")
@app.get("/api/index/cron")
async def news_cron(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_news_flow, os.getenv("LINE_USER_ID"))
    return "OK"
