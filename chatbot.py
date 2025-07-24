import os
import google.generativeai as genai
from dotenv import load_dotenv
import re


load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-2.0-flash")

def get_chatbot_response(user_message):
    try:
        convo = model.start_chat()

        convo.send_message(
            "You are a friendly, helpful movie chatbot."
            "You answer user questions about movies, genres, similar films, and where to watch."
            "Keep responses concise, helpful, and focused on movies."
        )

        convo.send_message(user_message)

        response_text = convo.last.text.strip()
        print(f'Gemini reply: {response_text}')
        return response_text

    except Exception as e:
        print(f"Gemini error: {e}")
        return "Oops! Something went wrong. Try again later."


def clean_response(text):
    # Remove bold/italic
    text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)
    # Replace bullet star with dash
    text = re.sub(r'^\s*\*\s+', '- ', text, flags=re.MULTILINE)
    return text

