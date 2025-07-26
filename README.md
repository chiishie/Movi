# 🎬 Movie Journal

A simple web app to search for movies, save them to your personal journal, and explore detailed information powered by the TMDB API.

🚀 **Live Site**: [https://seo-project-2.onrender.com/](https://seo-project-2.onrender.com/)

## Features
- 🔍 Search for movies by title
- 💾 Save and manage your movie list
- 📄 View detailed pages with genre info and summaries
- 🤖 AI-powered movie recommendations based on your ratings
- 💬 Interactive chatbot for movie discussions
- ⭐ Rate movies and get personalized suggestions

## Movie Recommendation System
The app now includes an intelligent recommendation system that:
- Analyzes your movie ratings using content-based filtering
- Uses TF-IDF vectorization to understand movie content and themes
- Provides personalized recommendations based on your preferences
- Falls back to popular movies for new users
- Automatically retrains when you add new ratings

## Technology Stack
- **Backend**: Flask, Python
- **Database**: SQLite
- **APIs**: TMDB API, YouTube API
- **Machine Learning**: scikit-learn, pandas
- **Frontend**: HTML, CSS, JavaScript, Bootstrap

## Installation

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up your TMDB API key in a `.env` file:
   ```
   TMDB_API_KEY=your_api_key_here
   ```
4. Run the application:
   ```bash
   python app.py
   ```

## Usage

1. **Register/Login**: Create an account or log in to save your preferences
2. **Search Movies**: Use the search bar to find movies
3. **Rate Movies**: Give ratings to movies you've watched
4. **Get Recommendations**: Visit the Recommendations page for personalized suggestions
5. **Chat with AI**: Use the chatbot for movie discussions and recommendations

## Testing the Recommendation Model

Run the test script to verify the recommendation system:
```bash
python test_model.py
```

---

*Made as part of the SEO Tech Developer Program.*
