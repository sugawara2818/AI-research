import os
import time
import json
import sys
from datetime import datetime
from typing import List, Dict

from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from google.api_core import exceptions
import google.generativeai as genai
import requests

# Diagnostics: Print sys.path and installed modules
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")
try:
    import fastapi
    print(f"FastAPI version: {fastapi.__version__}")
except ImportError:
    print("FATAL: FastAPI is NOT installed in the environment.")

app = FastAPI()

# --- Core Logic Classes ---

class Researcher:
    def __init__(self):
        self.tavily_key = os.getenv("TAVILY_API_KEY")
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=self.gemini_key)
        self.model = genai.GenerativeModel("gemini-flash-latest")

    def search_news(self, query: str = "latest AI technology trends and research 2024-2025") -> List[Dict]:
        print(f"Searching for: {query}")
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": 5
        }
        res = requests.post(url, json=payload)
        res.raise_for_status()
        return res.json().get('results', [])

    def filter_and_extract_facts(self, search_results: List[Dict]) -> str:
        context = "\n\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in search_results])
        prompt = f"""
あなたは高度なAI技術アナリストです。以下の検索結果から、開発者にとって技術的価値が高い「最新のAI動向」を3つ厳選し、それぞれの要点を客観的かつ論理的に整理してください。

【検索結果】
{context}

【出力形式】
以下の形式で出力してください：
1. [技術/トピック名]
   - 概要: 
   - 技術的ポイント: 
   - 開発者への影響/価値: 
   - ソースURL:

余計な挨拶は不要です。技術的密度を高めてください。
"""
        for attempt in range(3):
            try:
                response = self.model.generate_content(prompt)
                return response.text
            except exceptions.ResourceExhausted:
                if attempt == 2: raise
                time.sleep(300)
            except Exception as e:
                raise e

class Reporter:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("gemini-flash-latest")

    def generate_report(self, facts: str) -> str:
        current_date = datetime.now().strftime("%Y年%m月%d日")
        prompt = f"""
あなたは高度なAI技術ライターです。
現在の日付は **{current_date}** です。この日付をレポートのタイトルに使用してください。

以下の背景データをもとに、ITエンジニア向けの「週刊AI技術サマリー」を作成してください。
内容は客観的事実に基づき、推測を避け、論理的に構成してください。

【事実データ】
{facts}

【レポートの構成】
- タイトル: {current_date} AI技術動向レポート
- サマリー（3行以内）
- 各トピックの詳細分析
- 結論/考察

読みやすさを重視しつつ、専門用語は適切に使用してください。
"""
        for attempt in range(3):
            try:
                response = self.model.generate_content(prompt)
                return response.text
            except exceptions.ResourceExhausted:
                if attempt == 2: raise
                time.sleep(300)
            except Exception as e:
                raise e

class Notifier:
    def __init__(self):
        self.token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        self.user_id = os.getenv("LINE_USER_ID")
        self.url = "https://api.line.me/v2/bot/message/push"

    def send_line_notification(self, text: str):
        if not self.token or not self.user_id:
            return
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
        chunks = [text[i:i+4500] for i in range(0, len(text), 4500)]
        for chunk in chunks:
            payload = {"to": self.user_id, "messages": [{"type": "text", "text": chunk}]}
            try:
                res = requests.post(self.url, headers=headers, json=payload)
                res.raise_for_status()
            except Exception as e:
                print(f"LINE failure: {e}")

# --- API and Webhook Setup ---

channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(channel_access_token or "dummy")
handler = WebhookHandler(channel_secret or "dummy")

def perform_research_and_notify():
    try:
        researcher = Researcher()
        results = researcher.search_news()
        facts = researcher.filter_and_extract_facts(results)
        reporter = Reporter()
        report = reporter.generate_report(facts)
        notifier = Notifier()
        notifier.send_line_notification(report)
    except Exception as e:
        print(f"Flow error: {e}")

@app.get("/")
async def health_check():
    return {
        "status": "Webhook is running (Single File Mode)",
        "diagnostics": {
            "fastapi": "installed" if "fastapi" in sys.modules else "missing",
            "python": sys.version,
            "env_keys": {
                "line_token": "set" if channel_access_token else "missing",
                "tavily": "set" if os.getenv("TAVILY_API_KEY") else "missing"
            }
        }
    }

@app.get("/api/index/cron")
@app.get("/cron")
async def cron_trigger(request: Request):
    perform_research_and_notify()
    return {"status": "Cron started"}

@app.post("/")
@app.post("/api/index")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature")
    if not signature: raise HTTPException(status_code=400)
    body = (await request.body()).decode("utf-8")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    if any(k in user_msg for k in ["ニュース", "出来事", "リサーチ", "教えて"]):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="了解しました！リサーチを開始します。"))
        perform_research_and_notify()
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="こんにちは！「AIニュース教えて」と話しかけてください！"))
