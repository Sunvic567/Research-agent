from langchain_google_genai import ChatGoogleGenerativeAI
from settings.config import  google_key

llm = ChatGoogleGenerativeAI(
    api_key=google_key,
    model="gemini-2.5-flash",   
    temperature=0.3,
    max_output_tokens=1024,
)
