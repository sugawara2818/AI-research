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

# Diagnostics
try:
    import fastapi
    print(f"FastAPI version: {fastapi.__version__}")
except ImportError:
    print("FATAL: FastAPI is NOT installed.")

app = FastAPI()

# --- Shared Utilities ---

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
        # Expand search to include macro factors and world news
        search_query = f"{query} 株価 マクロ経済 世界情勢 決算 注目銘柄 stock price macro economy geopolitical earnings outlook"
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": search_query,
            "search_depth": "advanced",
            "max_results": 7 # Increased for broader context
        }
        res = requests.post(url, json=payload)
        res.raise_for_status()
        return res.json().get('results', [])

    def extract_stock_insights(self, search_results: List[Dict], query: str) -> str:
        context = "\n\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in search_results])
        prompt = f"""
あなたは伝説的な投資戦略家（ストラテジスト）です。以下の検索結果に基づき、銘柄「{query}」に関連する情報だけでなく、それを包囲する「世界情勢・マクロ経済」の視点を含めて、多角的な分析を行なってください。

【検索結果】
{context}

【分析の必須要件】
1. **世界情勢・マクロ環境**: 米国金利、インフレ、地政学リスク、原油価格、為替動向など、ターゲット銘柄に影響を与える外部環境を整理してください。
2. **多角的な見解**: 単一の結論ではなく、強気派・弱気派それぞれの視点や、市場の様々な思惑を抽出してください。
3. **個別銘柄分析**: 業績、決算、財務指標、競争優位性を鋭く評価してください。
4. **注目銘柄・セクターの提示**: 客観的データに基づき、現在の環境下で「特に注目すべき関連銘柄やセクター」を具体的に挙げてください。

客観性を保ちつつも、投資家が「次の一手」を判断できるような鋭いインサイトを出力してください。挨拶は不要です。
"""
        for model_name in self.models_to_try:
            try:
                model = genai.GenerativeModel(model_name)
                return model.generate_content(prompt).text
            except: continue
        raise Exception("Stock分析フェーズでエラーが発生しました。")

class StockReporter:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

    def generate_stock_report(self, insights: str, query: str) -> str:
        current_date = datetime.now().strftime("%Y年%m月%d日")
        prompt = f"""
あなたは機関投資家向けの調査報告書を作成するシニア・エクイティ・アナリストです。
以下の分析データをもとに、銘柄「{query}」の「株式調査レポート」を完成させてください。

【分析データ】
{insights}

【レポートの構成案】
1. **【{query}】 株式調査レポート ({current_date})**
2. **エグゼクティブ・サマリー**: 今、この銘柄で何が起きているのか？（3行以内）
3. **重点分析項目**: 業績、材料、財務状況、市場ポジションの深掘り。
4. **リスクとチャンス**: 投資家が考慮すべき上値余地と底値リスク。
5. **結論・考察**: 今後の株価の見通しについての論理的な展望。
6. **リソース・ソース**: 参考URLや関連トピックの紹介。

読みやすさと格調高さを両立させ、エンジニアや投資家も納得する論理的な構成にしてください。Markdown形式で出力してください。
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
        notifier.send_line_notification(report, target_id)
    except Exception as e:
        notifier.send_line_notification(f"ニュースリサーチ失敗: {str(e)}", target_id)

def run_news_consultation(query: str, target_id: str):
    notifier = Notifier()
    try:
        consultant = TechConsultant()
        advice = consultant.provide_advice(query)
        notifier.send_line_notification(advice, target_id)
    except Exception as e:
        notifier.send_line_notification(f"技術相談失敗: {str(e)}", target_id)

def run_stock_flow(query: str, target_id: str):
    notifier = Notifier()
    try:
        researcher = StockResearcher()
        reporter = StockReporter()
        results = researcher.search_stock_news(query)
        insights = researcher.extract_stock_insights(results, query)
        report = reporter.generate_stock_report(insights, query)
        notifier.send_line_notification(report, target_id)
    except Exception as e:
        notifier.send_line_notification(f"株分析失敗: {str(e)}", target_id)

def run_stock_consultation(query: str, target_id: str):
    notifier = Notifier()
    try:
        consultant = InvestmentConsultant()
        advice = consultant.provide_advice(query)
        notifier.send_line_notification(advice, target_id)
    except Exception as e:
        notifier.send_line_notification(f"投資相談失敗: {str(e)}", target_id)

# --- Webhook Handlers ---

channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(channel_access_token or "dummy")
line_handler = WebhookHandler(channel_secret or "dummy")

# Helper to route based on path
@app.post("/api/webhook")
@app.post("/api/index")
async def news_webhook(request: Request, background_tasks: BackgroundTasks):
    signature = request.headers.get("X-Line-Signature")
    body = (await request.body()).decode("utf-8")
    
    @line_handler.add(MessageEvent, message=TextMessage)
    def handle_news(event):
        msg = event.message.text
        uid = event.source.user_id
        if any(k in msg for k in ["作りたい", "おすすめ", "技術", "相談"]):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="技術的なご相談ですね。検討します…"))
            background_tasks.add_task(run_news_consultation, msg, uid)
        elif any(k in msg for k in ["ニュース", "リサーチ", "教えて"]):
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
        
        # Check for 4-digit stock codes (e.g., 7203) or keywords
        is_stock_code = msg.isdigit() and len(msg) == 4
        
        if is_stock_code or any(k in msg for k in ["株", "銘柄", "分析", "決算", "いくら"]):
            target_name = f"銘柄コード {msg}" if is_stock_code else msg
            line_bot_api.reply_message(
                event.reply_token, 
                TextSendMessage(text=f"「{target_name}」をプロの視点で分析します！少々お待ちください📈")
            )
            background_tasks.add_task(run_stock_flow, target_name, uid)
            
        elif any(k in msg for k in ["相談", "投資", "買い", "売り"]):
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="投資戦略のアドバイスを用意します。"))
            background_tasks.add_task(run_stock_consultation, msg, uid)
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="銘柄分析や投資相談をどうぞ！"))

    try:
        line_handler.handle(body, signature)
    except: pass
    return "OK"

@app.get("/")
async def health():
    return {"status": "Universal AI Bot is running. Endpoints: /api/webhook, /api/stock"}

@app.get("/cron")
@app.get("/api/index/cron")
async def news_cron(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_news_flow, os.getenv("LINE_USER_ID"))
    return "OK"
