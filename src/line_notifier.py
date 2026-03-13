import os
import requests
from dotenv import load_dotenv

load_dotenv()

class LineNotifier:
    def __init__(self):
        self.token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        self.user_id = os.getenv("LINE_USER_ID")
        self.api_url = "https://api.line.me/v2/bot/message/push"

    def notify(self, message: str) -> bool:
        """
        Send a push message to a specific LINE user.
        """
        if not self.token or not self.user_id:
            print("Error: LINE_CHANNEL_ACCESS_TOKEN or LINE_USER_ID not set.")
            return False

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }

        # LINE messages have a 5000 character limit per bubble.
        # For simplicity, we send one message. If the report is too long, it should be chunked.
        data = {
            "to": self.user_id,
            "messages": [
                {
                    "type": "text",
                    "text": message[:5000] # Truncate if too long for a single message
                }
            ]
        }

        print(f"Sending notification to LINE user: {self.user_id}")
        response = requests.post(self.api_url, headers=headers, json=data)
        
        if response.status_code == 200:
            print("Notification sent successfully.")
            return True
        else:
            print(f"Failed to send notification. Status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False

if __name__ == "__main__":
    notifier = LineNotifier()
    notifier.notify("Test message from AI News Reporter.")
