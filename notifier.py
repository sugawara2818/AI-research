import os
import requests

class Notifier:
    def __init__(self):
        self.token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        self.user_id = os.getenv("LINE_USER_ID")
        self.url = "https://api.line.me/v2/bot/message/push"

    def send_line_notification(self, text: str):
        """LINEにレポートを送信する。文字数制限(5000文字)を考慮し、必要なら分割する。"""
        if not self.token or not self.user_id:
            print("Error: LINE credentials not found.")
            return

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

        # LINEのpushメッセージ制限（1回5000文字）に配慮
        chunks = [text[i:i+4500] for i in range(0, len(text), 4500)]
        
        for chunk in chunks:
            payload = {
                "to": self.user_id,
                "messages": [
                    {
                        "type": "text",
                        "text": chunk
                    }
                ]
            }
            try:
                response = requests.post(self.url, headers=headers, json=payload)
                response.raise_for_status()
                print("LINE notification sent successfully.")
            except Exception as e:
                print(f"Failed to send LINE notification: {e}")

if __name__ == "__main__":
    notifier = Notifier()
    notifier.send_line_notification("これは自動生成されたテストレポートです。")
