import os
import json
from typing import List, Dict
import google.generativeai as genai
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

class AINewsReporter:
    def __init__(self):
        self.tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("gemini-1.5-pro")

    def search_news(self, query: str = "latest AI technology breakthroughs machine learning research", days: int = 1) -> List[Dict]:
        """
        Search for the latest AI news using Tavily.
        """
        print(f"Searching for AI news with query: {query}")
        # Search for AI news specifically
        response = self.tavily.search(
            query=query,
            search_depth="advanced",
            time_range="day",
            max_results=10
        )
        return response.get("results", [])

    def synthesize_report(self, news_items: List[Dict]) -> str:
        """
        Synthesize a high-density technical report from news items using Gemini 1.5 Pro.
        """
        if not news_items:
            return "No significant AI news found today."

        context = "\n".join([
            f"Title: {item['title']}\nSnippet: {item['content']}\nURL: {item['url']}\n---"
            for item in news_items
        ])

        prompt = f"""
あなたは高度な技術知識を持つAIエンジニア向けのリサーチアシスタントです。
以下のニュース情報に基づき、開発者が技術的価値を即座に判断できる高密度なテクニカルレポートを生成してください。

【制約事項】
- 共感、装飾的な表現、導入文、結びの言葉は一切排除せよ。
- 客観的事実と論理的整合性を最優先せよ。
- 重要なトピックを厳選し、箇条書き（Markdown形式）で構成せよ。
- 各トピックは以下の構造を持つこと：
  - [見出し]: テクノロジー名やプロジェクト名
  - [概要]: 何が達成されたか（定量的かつ具体的な記述）
  - [技術的ブレイクスルー]: 従来技術との違い、アーキテクチャ上の工夫（推論を含む）
  - [影響/展望]: 実装や業界への具体的な影響
  - [参照]: URL

ニュース情報：
{context}
"""
        print("Synthesizing report using Gemini...")
        response = self.model.generate_content(prompt)
        return response.text

if __name__ == "__main__":
    reporter = AINewsReporter()
    news = reporter.search_news()
    report = reporter.synthesize_report(news)
    print("\n--- Generated Report ---\n")
    print(report)
