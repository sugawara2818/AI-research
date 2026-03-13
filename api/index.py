import os
import time
import json
import sys
from datetime import datetime
from typing import List, Dict

from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from google.api_core import exceptions
import google.generativeai as genai
import requests

# Diagnostics: Print sys.path and installed modules
print(f"Python version: {sys.version}")
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
        # Use models confirmed by diagnostics
        self.models_to_try = [
            "models/gemini-2.0-flash", 
            "models/gemini-1.5-flash", 
            "models/gemini-1.5-flash-latest",
            "gemini-1.5-flash",
            "gemini-pro"
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
        error_details = []
        for model_name in self.models_to_try:
            for attempt in range(2):
                try:
                    print(f"Trying model: {model_name} (Attempt {attempt+1})")
                    self.model = genai.GenerativeModel(model_name)
                    response = self.model.generate_content(prompt)
                    return response.text
                except exceptions.NotFound as e:
                    error_details.append(f"{model_name}: NotFound - {str(e)}")
                    break 
                except exceptions.ResourceExhausted as e:
                    error_details.append(f"{model_name}: QuotaExceeded - {str(e)}")
                    if attempt == 1: break 
                    print(f"Gemini {model_name} Quota hit, waiting 30s...")
                    time.sleep(30)
                except Exception as e:
                    error_details.append(f"{model_name}: Error - {str(e)}")
                    if model_name == self.models_to_try[-1]: break
                    break
        
        failure_summary = " | ".join(error_details)
        raise Exception(f"All models failed. Details: {failure_summary}")

class Reporter:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.models_to_try = ["gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-pro"]
        self.model = genai.GenerativeModel(self.models_to_try[0])

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
                    error_details.append(f"{model_name}: Quota")
                    if attempt == 1: break
                    time.sleep(30)
                except Exception as e:
                    error_details.append(f"{model_name}: {str(e)}")
                    break
        raise Exception(f"Reporter failed. Details: {' | '.join(error_details)}")

class Notifier:
    def __init__(self):
        self.token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        self.user_id = os.getenv("LINE_USER_ID")
        self.url = "https://api.line.me/v2/bot/message/push"

    def send_line_notification(self, text: str):
        if not self.token or not self.user_id:
            print(f"Missing LINE info: token={bool(self.token)}, user_id={bool(self.user_id)}")
            return
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
        chunks = [text[i:i+4500] for i in range(0, len(text), 4500)]
        for chunk in chunks:
            payload = {"to": self.user_id, "messages": [{"type": "text", "text": chunk}]}
            try:
                res = requests.post(self.url, headers=headers, json=payload)
                res.raise_for_status()
                print("LINE notification sent successfully.")
            except Exception as e:
                print(f"LINE failure: {e}")

# --- API and Webhook Setup ---

channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
channel_secret = os.getenv("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(channel_access_token or "dummy")
line_handler = WebhookHandler(channel_secret or "dummy")

# Shared state to pass background tasks (Vercel workaround)
current_bg_tasks = None

def perform_research_and_notify():
    print("Background flow: Starting research...")
    notifier = Notifier()
    try:
        try:
            researcher = Researcher()
            try:
                results = researcher.search_news()
            except Exception as e:
                raise Exception(f"【Tavily検索エラー】: {str(e)}")
            
            try:
                facts = researcher.filter_and_extract_facts(results)
            except Exception as e:
                raise Exception(f"【Gemini抽出エラー】: {str(e)}")
        except Exception as e:
            # Re-raise to be caught by the outer block
            raise e

        try:
            reporter = Reporter()
            report = reporter.generate_report(facts)
        except Exception as e:
            raise Exception(f"【レポート生成エラー】: {str(e)}")

        try:
            notifier.send_line_notification(report)
        except Exception as e:
            raise Exception(f"【LINE送信エラー】: {str(e)}")

        print("Background flow: Finished successfully.")
    except Exception as e:
        import google.generativeai as gai
        lib_ver = getattr(gai, "__version__", "unknown")
        error_msg = f"システムの実行中にエラーが発生しました:\n{str(e)}\n(Lib: {lib_ver})"
        print(error_msg)
        try:
            notifier.send_line_notification(error_msg)
        except:
            pass

@app.get("/")
async def health_check():
    available_models = []
    try:
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
    except Exception as e:
        available_models = [f"Error listing: {str(e)}"]

    return {
        "status": "Webhook is running (Diagnostic Mode)",
        "diagnostics": {
            "fastapi": "installed",
            "lib_version": getattr(genai, "__version__", "unknown"),
            "available_models_count": len(available_models),
            "first_3_models": available_models[:3],
            "env_status": {
                "GEMINI_API_KEY": "set" if os.getenv("GEMINI_API_KEY") else "missing",
                "LINE_USER_ID": "set" if os.getenv("LINE_USER_ID") else "missing"
            }
        }
    }

@app.get("/api/index/cron")
@app.get("/cron")
async def cron_trigger(background_tasks: BackgroundTasks):
    background_tasks.add_task(perform_research_and_notify)
    return {"status": "Scheduled research started in background"}

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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return "OK"

@line_handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    if any(k in user_msg for k in ["ニュース", "出来事", "リサーチ", "教えて"]):
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="了解しました！リサーチを開始します。結果は後ほどこのチャットに送ります。（約1〜2分かかります）")
        )
        # Prevent blocking the webhook response
        if current_bg_tasks:
            current_bg_tasks.add_task(perform_research_and_notify)
        else:
            # Fallback for sync environments
            import threading
            threading.Thread(target=perform_research_and_notify).start()
    else:
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="こんにちは！「AIのニュース教えて」など、リサーチの依頼をしてください！")
        )
