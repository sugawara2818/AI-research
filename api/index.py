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

# Diagnostics: Print version
try:
    import fastapi
    print(f"FastAPI version: {fastapi.__version__}")
except ImportError:
    print("FATAL: FastAPI is NOT installed.")

app = FastAPI()

# --- Core Logic Classes ---

class Researcher:
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
特に、具体的な「おすすめのツール」、「ライブラリ」、「注目すべきX(Twitter)アカウントや重要人物」の情報があれば積極的に抽出してください。

【検索結果】
{context}

【出力形式】
以下の形式で出力してください：
1. [技術/トピック名]
   - 概要: 
   - 技術的ポイント: 
   - 開発者への影響/価値: 
   - おすすめツール/関連リンク: (あれば)
   - 注目アカウント/人物: (あれば、外部へのリンク等)
   - ソースURL:

余計な挨拶は不要です。技術的密度を高めてください。
"""
        error_details = []
        for model_name in self.models_to_try:
            for attempt in range(2):
                try:
                    self.model = genai.GenerativeModel(model_name)
                    response = self.model.generate_content(prompt)
                    return response.text
                except exceptions.NotFound as e:
                    error_details.append(f"{model_name}: NotFound")
                    break 
                except exceptions.ResourceExhausted as e:
                    error_details.append(f"{model_name}: QuotaExceeded")
                    if attempt == 1: break 
                    time.sleep(30)
                except Exception as e:
                    error_details.append(f"{model_name}: {str(e)[:50]}")
                    break
        
        failure_summary = " | ".join(error_details)
        raise Exception(f"All models failed. Details: {failure_summary}")

class Reporter:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.models_to_try = [
            "models/gemini-2.5-flash", 
            "models/gemini-2.0-flash-exp", 
            "models/gemini-1.5-flash"
        ]
        self.model = genai.GenerativeModel(self.models_to_try[0])

    def generate_report(self, facts: str) -> str:
        current_date = datetime.now().strftime("%Y年%m月%d日")
        prompt = f"""
あなたは高度なAI技術ライターです。
現在の日付は **{current_date}** です。この日付をレポートのタイトルに使用してください。

以下の背景データをもとに、ITエンジニア向けの「週刊AI技術サマリー」を作成してください。
具体的なツール名や外部リンク、Xアカウントなどのメタ情報を「リソース」として整理し、読者がすぐにアクションを起こせるように構成してください。

【事実データ】
{facts}

【レポートの構成】
- タイトル: {current_date} AI技術動向レポート
- サマリー（3行以内）
- 各トピックの詳細分析（ツール・リンク含む）
- おすすめリソース & 注目アカウント一覧
- 結論/考察

読みやすさを重視しつつ、専門用語は適切に使用してください。
"""
        error_details = []
        for model_name in self.models_to_try:
            for attempt in range(2):
                try:
                    self.model = genai.GenerativeModel(model_name)
                    response = self.model.generate_content(prompt)
                    return response.text
                except exceptions.NotFound:
                    error_details.append(f"{model_name}: NotFound")
                    break
                except exceptions.ResourceExhausted:
                    error_details.append(f"{model_name}: Quota")
                    if attempt == 1: break
                    time.sleep(30)
                except Exception as e:
                    error_details.append(f"{model_name}: {str(e)[:50]}")
                    break
        raise Exception(f"Reporter failed. Details: {' | '.join(error_details)}")

class Consultant:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("models/gemini-2.5-flash")

    def provide_advice(self, user_query: str) -> str:
        prompt = f"""
あなたは百戦錬磨のITソリューションアーキテクトです。
ユーザーからの「〜を作りたい」「おすすめの技術はある？」といった相談に対し、具体的かつ実戦的なアドバイスを行なってください。

【相談内容】
{user_query}

【回答の指針】
1. 推奨する技術スタック（フロントエンド、バックエンド、DB、インフラ、AI-API等）
2. その技術を選ぶ理由とメリット
3. 開発の第一歩としてすべきこと
4. 注意点や落とし穴
5. 参考になるGitHubリポジトリやドキュメント、Xアカウント等の外部リンク

親しみやすくもプロフェッショナルなトーンで回答してください。
"""
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            return f"アドバイスの生成中にエラーが発生しました: {str(e)}"

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

# --- API and Webhook Setup ---

channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(channel_access_token or "dummy")
line_handler = WebhookHandler(channel_secret or "dummy")

current_bg_tasks = None

def perform_research_and_notify(target_id: Optional[str] = None):
    notifier = Notifier()
    try:
        researcher = Researcher()
        results = researcher.search_news()
        facts = researcher.filter_and_extract_facts(results)
        reporter = Reporter()
        report = reporter.generate_report(facts)
        notifier.send_line_notification(report, target_id)
    except Exception as e:
        notifier.send_line_notification(f"システムの実行中にエラーが発生しました:\n{str(e)}", target_id)

def perform_consultation_and_notify(query: str, target_id: Optional[str] = None):
    notifier = Notifier()
    try:
        consultant = Consultant()
        advice = consultant.provide_advice(query)
        notifier.send_line_notification(advice, target_id)
    except Exception as e:
        notifier.send_line_notification(f"相談フェーズでエラーが発生しました: {str(e)}", target_id)

@app.get("/")
async def health_check():
    return {"status": "Webhook is running (Multi-User-Safe Mode v4)"}

@app.get("/api/index/cron")
@app.get("/cron")
async def cron_trigger(background_tasks: BackgroundTasks):
    background_tasks.add_task(perform_research_and_notify) # Defaults to owner
    return {"status": "Scheduled research started for owner"}

@app.post("/")
@app.post("/api/index")
@app.post("/api/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
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
def handle_message(event):
    user_msg = event.message.text
    user_id = event.source.user_id
    
    # Consultation logic
    if any(k in user_msg for k in ["作りたい", "おすすめ", "技術", "方法", "相談", "アドバイス"]):
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="技術的なご相談ですね！アーキテクトとして最適な構成を検討します。少々お待ちください…")
        )
        if current_bg_tasks:
            current_bg_tasks.add_task(perform_consultation_and_notify, user_msg, user_id)
    
    # Research logic
    elif any(k in user_msg for k in ["ニュース", "出来事", "リサーチ", "教えて"]):
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="了解しました！リサーチを開始します。おすすめのツールやURLも含めて整理しますね。")
        )
        if current_bg_tasks:
            current_bg_tasks.add_task(perform_research_and_notify, user_id)
    
    else:
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="こんにちは！「AIニュースを教えて」や「〜というツールを作りたいけどおすすめの技術ある？」など、何でも聞いてください！")
        )
