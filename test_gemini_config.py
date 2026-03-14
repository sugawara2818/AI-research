import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def test_stable_model_search():
    model_name = "models/gemini-2.0-flash-exp"
    try:
        print(f"Testing model: {model_name}")
        # Standard tool name for Google Search in Python SDK is google_search_retrieval
        model = genai.GenerativeModel(
            model_name=model_name,
            tools=[{"google_search_retrieval": {}}]
        )
        
        response = model.generate_content("What is the current stock price of Apple?")
        print("Success!")
        print(response.text)
    except Exception as e:
        print(f"Error caught: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_stable_model_search()
