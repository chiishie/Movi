import os
import google.generativeai as genai
from dotenv import load_dotenv
import re


load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-2.0-flash")


def get_chatbot_response(user_message, context, history=None):
    try:

        if not context:
            context_str = "The user has not watched any movies or TV shows yet."
        else:
            context_str = "Here is a list of movies and TV shows the user has watched, you can use them as context for your response."

            for media in context:
                context_str += f"Movie or TV show: {media['title']} \n"
                context_str += f"Rating: {media['rating']}\n"
                context_str += f"Genres: {media['genre_names']}\n"

        history_str = ''
        if history:
            history_str = f'chat history:\n'
            for h in history:
                role = "User" if h['role'] == 'user' else "Assistant"
                history_str += f"{role}: {h['message']}\n"

        prompt  = (
            "You are a friendly, helpful movie chatbot."
            "You answer user questions about movies, genres, similar films, and where to watch."
            "Keep responses concise, helpful, and focused on movies."
            f"Here is the context: {context_str}"
            f"Here is the conversation so far: {history_str}"
            f"User: {user_message}\nAssistant: "
        )

        response = model.generate_content(prompt)
        response_text = response.text.strip()
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