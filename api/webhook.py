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

# LINE Credentials from environment variables
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

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
        notifier = Notifier()
        notifier.send_line_notification(f"システムの自動実行中にエラーが発生しました: {str(e)}")

@app.get("/api/webhook/cron")
async def cron_trigger(request: Request):
    # Simple security check if needed - Vercel allows limiting cron access easily
    # But for simplicity, we trigger the flow
    perform_research_and_notify()
    return {"status": "Research flow triggered via Cron"}

@app.post("/api/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")
    
    body = await request.body()
    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
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
