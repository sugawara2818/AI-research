import os
import time
from datetime import datetime
import google.generativeai as genai
from google.api_core import exceptions
from dotenv import load_dotenv

load_dotenv()

class Reporter:
    def __init__(self):
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("gemini-flash-latest")

    def generate_report(self, facts: str) -> str:
        """抽出された事実をもとに、完成されたレポートを作成する"""
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
            except exceptions.ResourceExhausted as e:
                if attempt == 2: raise
                wait_time = 300  # 5 minutes wait
                print(f"Quota exceeded. Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                raise

if __name__ == "__main__":
    facts_example = """
1. OpenAI SoraのAPIプレビュー開始
   - 概要: テキストから動画を生成するモデルSoraのAPIが限定公開
   - 技術的ポイント: Diffusion Transformerアーキテクチャによる時間的整合性の維持
2. Google Gemini 1.5 Proのコンテキストウィンドウ拡張
   - 概要: 200万トークンのコンテキストを処理可能に
   - 技術的ポイント: 混合専門家（MoE）モデルによる効率的な長文推論
"""
    reporter = Reporter()
    report = reporter.generate_report(facts_example)
    print(report)
