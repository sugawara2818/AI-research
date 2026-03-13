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
        # Append .T for Tokyo Stock Exchange if it's a numeric code to avoid hallucination
        processed_query = query
        if "銘柄コード" in query:
            code = query.replace("銘柄コード", "").strip()
            processed_query = f"{code}.T {code} 証券コード"

        search_query = (
            f"{processed_query} 株価 決算短信 業績推移 財務分析 チャート動向 市場ニュース 世界情勢 "
            f"stock price {processed_query} financial stats analyst ratings technical analysis peer comparison market impacts"
        )
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": search_query,
            "search_depth": "advanced",
            "max_results": 15 # High density search for precision
        }
        res = requests.post(url, json=payload)
        res.raise_for_status()
        return res.json().get('results', [])

    def extract_stock_insights(self, search_results: List[Dict], query: str) -> str:
        context = "\n\n".join([f"Source: {r['url']}\nContent: {r['content']}" for r in search_results])
        prompt = f"""
あなたは極めて優秀かつ冷徹なシニア・リサーチアナリストです。
銘柄「{query}」について、以下の検索結果をもとに「超高精度・超詳細な分析」を行なってください。

【絶対遵守：銘柄の同一性確認】
検索結果にターゲット以外の銘柄（似たコードや名前）が混じっていることが多々あります。
必ず「証券コード」と「企業名」を照合し、ターゲット銘柄と確信できる情報のみを抽出してください。混同はプロとして致命的です。

【分析の深化項目】
1. **財務・決算の詳細分析**: 
   売上高、営業利益、純利益の直近数値。前年同期比、進捗率。通期予想の上方/下方修正の有無。
2. **定量的評価データの収集**: 
   PER、PBR、ROE、配当利回り、自己資本比率の具体的数値。業界平均や過去平均との比較。
3. **テクニカル・需給状況の診断**: 
   現在のチャート形状、支持線・抵抗線。移動平均線との乖離率。出来高の推移、信用買い残・売り残の状況。
4. **マクロ・外部環境の波及経路**: 
   今、世界のどこで起きている「何（金利、為替、紛争、政策等）」が、この企業のサプライチェーンや最終利益にどうヒットするのかを具体的に特定してください。
5. **情報の峻別**: 
   些末なニュースは捨て、株価のメインドライバー（材料）を1〜2点に絞り込んで深掘りしてください。

【5段階評価の準備】
「成長性」「収益性」「安全性」「割安性」「外部環境耐性」の5項目を★で表すための具体的根拠を、検索結果から漏れなく抽出してください。
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
