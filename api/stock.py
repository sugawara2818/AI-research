import os
import time
import json
import sys
from datetime import datetime
from typing import List, Dict, Optional

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from google.api_core import exceptions
import google.generativeai as genai
import requests

app = FastAPI()

# --- Stock Logic Classes ---

class StockResearcher:
    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=self.gemini_key)
        self.models_to_try = [
            "models/gemini-2.5-flash", 
            "models/gemini-2.0-flash-exp", 
            "models/gemini-1.5-flash"
        ]
        self.model = genai.GenerativeModel(self.models_to_try[0])

    def search_stock_news(self, query: str) -> List[Dict]:
        print(f"Searching stock info for: {query}")
        # Improve query for better stock results
        search_query = f"{query} 株価 決算 業績 ニュース stock price earnings news"
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": search_query,
            "search_depth": "advanced",
            "max_results": 5
        }
        res = requests.post(url, json=payload)
        res.raise_for_status()
        return res.json().get('results', [])

    def extract_stock_insights(self, search_results: List[Dict], query: str) -> str:
        context = "\n\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in search_results])
        prompt = f"""
あなたは百戦錬磨の株式アナリストです。以下の検索結果から、銘柄「{query}」または関連市場に関する最新の重要情報を抽出・分析してください。

【検索結果】
{context}

【分析のポイント】
1. 最新の株価動向や決算内容
2. 株価に影響を与えているポジティブ/ネガティブな要因
3. 今後の注目材料（発表予定の指標やイベント）
4. 具体的な数値（PER, PBR, 配当利回り等の言及があれば）

余計な挨拶は不要です。プロ仕様の鋭い分析を行なってください。
"""
        for model_name in self.models_to_try:
            try:
                self.model = genai.GenerativeModel(model_name)
                response = self.model.generate_content(prompt)
                return response.text
            except Exception:
                continue
        raise Exception("Stock insights extraction failed on all models.")

class StockReporter:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

    def generate_stock_report(self, insights: str, query: str) -> str:
        current_date = datetime.now().strftime("%Y年%m月%d日")
        prompt = f"""
あなたは投資顧問会社のシニアアナリストです。
銘柄「{query}」に関する最新の調査報告書を作成してください。

【背景データ】
{insights}

【レポート形式】
- タイトル: 【{query}】 株式調査レポート ({current_date})
- エグゼクティブ・サマリー (簡潔な結論)
- 詳細分析 (業績、市場環境、材料)
- 投資家としての視点 (リスクとチャンス)
- 参考文献/ソースリンク

専門用語（ボラティリティ、ファンダメンタルズ等）を適切に使いつつ、論理的で分かりやすい報告書に仕上げてください。
"""
        response = self.model.generate_content(prompt)
        return response.text

class StockConsultant:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

    def provide_investment_advice(self, user_query: str) -> str:
        prompt = f"""
あなたは経験豊富なファイナンシャル・アドバイザーです。
ユーザーからの投資や銘柄選びに関する相談に対し、多角的な視点からアドバイスを行なってください。

【相談内容】
{user_query}

【回答のステップ】
1. 現状の市場環境の要約
2. 推奨されるセクターや銘柄選びの考え方
3. 初心者〜中級者が確認すべき具体的な指標
4. リスク管理のアドバイス
5. 便利な投資分析ツールや情報源の紹介

※「投資は自己責任である」という免責事項を優しく添えてください。
"""
        response = self.model.generate_content(prompt)
        return response.text

class Notifier:
    def __init__(self):
        self.token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        self.url = "https://api.line.me/v2/bot/message/push"

    def send_line_notification(self, text: str, target_id: str):
        if not self.token or not target_id: return
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
        chunks = [text[i:i+4500] for i in range(0, len(text), 4500)]
        for chunk in chunks:
            payload = {"to": target_id, "messages": [{"type": "text", "text": chunk}]}
            requests.post(self.url, headers=headers, json=payload)

# --- Webhook and Background Processing ---

channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(channel_access_token or "dummy")
line_handler = WebhookHandler(channel_secret or "dummy")

current_bg_tasks = None

def perform_stock_research_and_notify(query: str, target_id: str):
    notifier = Notifier()
    try:
        researcher = StockResearcher()
        results = researcher.search_stock_news(query)
        insights = researcher.extract_stock_insights(results, query)
        reporter = StockReporter()
        report = reporter.generate_stock_report(insights, query)
        notifier.send_line_notification(report, target_id)
    except Exception as e:
        notifier.send_line_notification(f"株リサーチ中にエラーが発生しました: {str(e)}", target_id)

def perform_investment_consultation(query: str, target_id: str):
    notifier = Notifier()
    try:
        consultant = StockConsultant()
        advice = consultant.provide_investment_advice(query)
        notifier.send_line_notification(advice, target_id)
    except Exception as e:
        notifier.send_line_notification(f"投資相談中にエラーが発生しました: {str(e)}", target_id)

@app.get("/")
async def health():
    return {"status": "Stock AI Webhook is running"}

@app.post("/")
@app.post("/api/stock")
@app.post("/api/webhook")
async def stock_webhook(request: Request, background_tasks: BackgroundTasks):
    signature = request.headers.get("X-Line-Signature")
    if not signature: raise HTTPException(status_code=400)
    body = (await request.body()).decode("utf-8")
    global current_bg_tasks
    current_bg_tasks = background_tasks
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400)
    return "OK"

@line_handler.add(MessageEvent, message=TextMessage)
def handle_stock_message(event):
    user_msg = event.message.text
    user_id = event.source.user_id
    
    # Check if it's a specific stock/news inquiry
    if any(k in user_msg for k in ["株", "銘柄", "決算", "分析", "いくら"]):
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=f"「{user_msg}」について調査を開始します。プロの視点で分析レポートを作成しますので、1〜2分ほどお待ちください…📈")
        )
        if current_bg_tasks:
            current_bg_tasks.add_task(perform_stock_research_and_notify, user_msg, user_id)
            
    # Check if it's investment advice
    elif any(k in user_msg for k in ["相談", "おすすめ", "投資", "買い", "売り"]):
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="投資戦略のご相談ですね。市場環境を踏まえたアドバイスをまとめます。少々お待ちください。")
        )
        if current_bg_tasks:
            current_bg_tasks.add_task(perform_investment_consultation, user_msg, user_id)
    
    else:
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="こんにちは！「トヨタの株について教えて」や「おすすめの高配当株は？」など、銘柄の分析や投資相談を承ります！")
        )
