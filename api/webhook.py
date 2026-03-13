import os
from fastapi import FastAPI, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from researcher import Researcher
from reporter import Reporter
from notifier import Notifier
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Helper to get LINE API instances safely
def get_line_api():
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    secret = os.getenv("LINE_CHANNEL_SECRET")
    if not token or not secret:
        print(f"ERROR: Missing LINE credentials. Token: {'set' if token else 'empty'}, Secret: {'set' if secret else 'empty'}")
        return None, None
    return LineBotApi(token), WebhookHandler(secret)

def perform_research_and_notify():
    """Shared logic for both interactive commands and cron jobs"""
    print("Triggering research flow...")
    try:
        researcher = Researcher()
        results = researcher.search_news()
        facts = researcher.filter_and_extract_facts(results)
        
        reporter = Reporter()
        report = reporter.generate_report(facts)
        
        notifier = Notifier()
        notifier.send_line_notification(report)
        print("Flow completed successfully.")
    except Exception as e:
        print(f"Error in research flow: {e}")
        try:
            notifier = Notifier()
            notifier.send_line_notification(f"システムの自動実行中にエラーが発生しました: {str(e)}")
        except:
            pass

@app.get("/")
async def health_check():
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    secret = os.getenv("LINE_CHANNEL_SECRET")
    return {
        "status": "Webhook is running",
        "env_check": {
            "token": "present" if token else "missing",
            "secret": "present" if secret else "missing"
        }
    }

@app.get("/api/webhook/cron")
@app.get("/cron")
async def cron_trigger(request: Request):
    perform_research_and_notify()
    return {"status": "Cron execution started"}

@app.post("/")
@app.post("/api/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature")
    if not signature:
        print("Error: Missing X-Line-Signature header")
        raise HTTPException(status_code=400, detail="Missing signature")
    
    body = (await request.body()).decode("utf-8")
    line_bot_api, handler = get_line_api()
    
    if not handler:
        print("Error: LINE handler could not be initialized")
        raise HTTPException(status_code=500, detail="Server configuration error")
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Error: Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        print(f"Unexpected error in handler: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text
    
    # Check for keywords
    keywords = ["ニュース", "出来事", "リサーチ", "教えて", "news"]
    if any(k in user_msg for k in keywords):
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="了解しました！最新のAI情報をリサーチします。少々お待ちください...（1〜2分かかります）")
        )
        
        # Trigger research flow using the shared function
        perform_research_and_notify()
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="こんにちは！「AIニュース教えて」と話しかけていただければ、最新の技術動向をリサーチして報告します！")
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
