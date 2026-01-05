import os
from dotenv import load_dotenv

load_dotenv()

tavily_key = os.getenv("Tavily_API_KEY")
google_key = os.getenv("GOOGLE_API_KEY")
langsmith_key = os.getenv("LANGSMITH_API_KEY")