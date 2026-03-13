import os
import json
import time
from typing import List, Dict
from tavily import TavilyClient
import google.generativeai as genai
from google.api_core import exceptions

class Researcher:
    def __init__(self):
        self.tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = genai.GenerativeModel("gemini-flash-latest")

    def search_news(self, query: str = "latest AI technology trends and research 2024-2025") -> List[Dict]:
        """Tavilyを使って最新のAIニュースを検索する"""
        print(f"Searching for: {query}")
        response = self.tavily.search(query=query, search_depth="advanced", max_results=5)
        return response.get('results', [])

    def filter_and_extract_facts(self, search_results: List[Dict]) -> str:
        """Geminiを使って検索結果から重要な技術的事実のみを抽出する"""
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
            except exceptions.ResourceExhausted as e:
                if attempt == 2: raise
                wait_time = 300  # 5 minutes wait for free tier
                print(f"Quota exceeded. Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                raise

if __name__ == "__main__":
    researcher = Researcher()
    results = researcher.search_news()
    facts = researcher.filter_and_extract_facts(results)
    print("\n--- Extracted Facts ---\n")
    print(facts)
