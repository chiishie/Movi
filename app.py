from flask import Flask, render_template, abort, request, session, redirect, url_for, jsonify
from dotenv import load_dotenv
from search import TMDBClient
import database
import os
import requests
import json
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from chatbot import get_chatbot_response, clean_response
import uuid
import joblib
from model import MovieRecommender

app = Flask(__name__)
app.secret_key = os.urandom(24)
load_dotenv()

search_client = None
movies = []
recommender = None

# Run once at the start to fetch data from TMDB API
def init_app():
    global search_client, database, recommender

    # Initialize the database
    database = database.MovieRankerDB()

    # Initialize the TMDB client with the API key from environment variables
    api_key = os.getenv("TMDB_API_KEY")
    
    print(f"Loaded API key: '{api_key}'")

    search_client = TMDBClient(api_key=api_key)
    print(f"TMDBClient created with key: {search_client.api_key}")
    search_client.fetch_genres()
    # Run the initialization of the database to create tables if they don't exist
    database.init_db()
    
    # Initialize the recommendation model
    try:
        recommender = MovieRecommender()
        print("Movie recommendation model initialized successfully")
    except Exception as e:
        print(f"Error initializing recommendation model: {e}")
        recommender = None

init_app()

def add_movie(user_id,imdb_id,rating,title):
    conn = sqlite3.connect('movie_ranker.db')
    cursor = conn.cursor()
    #could add try except to check if the movie already exists
    cursor.execute('''
    INSERT INTO movies_list (user_id, imdb_id, rating, title)
    VALUES (?, ?, ?, ?)
    ''', (user_id, imdb_id, rating, title))
    conn.commit()

def get_or_make_user(username):
    conn = database.db_connect()
    user = conn.execute('SELECT * FROM users WHERE name = ?', (username,)).fetchone()
    if user is None:
        conn.execute('INSERT INTO users (name) VALUES (?)', (username,))
        conn.commit()
        user = conn.execute('SELECT * FROM users WHERE name = ?', (username,)).fetchone()
    conn.close()
    return user

def save_chat_message(user_id, role, message):
    conn = sqlite3.connect('movie_ranker.db')
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO chat_history (user_id, session_id, role, message)
    VALUES (?, ?, ?, ?)
    """, (user_id, session.get("chat_session"), role, message))
    conn.commit()
    conn.close()

def reset_chat_history(user_id, history):
    conn = sqlite3.connect('movie_ranker.db')
    cursor = conn.cursor()
    cursor.execute("""
    DELETE FROM chat_history WHERE user_id = ? AND session_id = ?""", user_id, session.get('chat_session', history))
    conn.commit()
    conn.close()

def get_chat_history(user_id):
    conn = sqlite3.connect('movie_ranker.db')
    cursor = conn.cursor()
    cursor.execute("""
    SELECT role, message FROM chat_history
    WHERE user_id = ? AND session_id = ?
    ORDER BY id ASC
    """, (user_id, session.get('chat_session')))
    history = cursor.fetchall()
    conn.close()
    return [{'role': r, "message": m} for r, m in history]

@app.route("/")
def search():
    global movies
    query = request.args.get('query')
    if query:
        movies = search_client.search_media(title=query)
        return render_template("search.html", movies=movies, query=query,is_discover=False)
    else:
        page = request.args.get('page', 1, type=int)
        movies = search_client.discover_mixed_media(page=page)
        next_page = page + 1
        return render_template("search.html", movies=movies, query=None, is_discover=True, next_page=next_page)


@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']
        if not username or not password:
            return render_template("login.html", error="Username and password are required.")
        user = database.get_user_by_username(username)
        if user is None or not check_password_hash(user['password'], password):
            return render_template("login.html", error="Invalid username or password.")
        session["user_id"] = user['id']
        session["username"] = user['name']
        if 'chat_session' not in session:
            session['chat_session'] = str(uuid.uuid4())
        return redirect(url_for("search"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("search"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if not username or not password:
            return render_template("register.html", error="Username and password are required.")
        hashed_password = generate_password_hash(password)
        success = database.add_user(username, hashed_password)
        if not success:
            return render_template("register.html", error="Username already exists.")

        user = database.get_user_by_username(username)
        session["user_id"] = user["id"]
        session["username"] = user["name"]
        return redirect(url_for("search"))
    return render_template("register.html")

@app.route("/my_movies.html")
def my_movies():
    global movies
    user_movies = database.get_user_movies(session.get("user_id"))
    # Add genre information to each movie
    movies = []
    for movie_row in user_movies:
        movie = dict(movie_row)  # Convert Row to dict for modification
        genre_ids = database.get_movie_genres(movie['id'])
        movie['genre_names'] = search_client.genre_ids_to_names(genre_ids)
        movies.append(movie)
    return render_template("my_movies.html", movies=movies, user_name=session.get("username"))

@app.route("/rate_movie/<int:movie_id>", methods=["POST"])
def rate_movie(movie_id):
    rating = request.form.get("rating")
    if rating and session.get("user_id") is not None:
        print(f"id: {session['user_id']}, movie_id: {movie_id}, rating: {rating}")
        global movies
        movie = next((m for m in movies if m["id"] == movie_id), None)
        database.add_media(movie)
        database.add_user_movies_by_id(session["user_id"], movie_id, rating)
        
        # Refresh the recommendation model when new ratings are added
        try:
            refresh_model()
            print(f"Recommendation model refreshed after rating movie {movie_id}")
        except Exception as e:
            print(f"Error refreshing recommendation model: {e}")
    elif rating:
        print("Not logged in")
        return redirect(url_for("login"))
    else:
        print("No rating provided")
    return redirect(url_for("movie_detail", movie_id=movie_id))

@app.route("/movie/<int:movie_id>")
def movie_detail(movie_id):
    # Look up the movie in your database or list
    global movies
    movie = next((m for m in movies if m["id"] == movie_id), None)
    
    # If not in current movies list, try to get from database
    if movie is None:
        movie_data = database.get_movie_data(movie_id)
        if movie_data:
            movie = dict(movie_data)
        else:
            # Try to fetch from TMDB API
            try:
                from search import TMDBClient
                import os
                from dotenv import load_dotenv
                
                load_dotenv()
                api_key = os.getenv("TMDB_API_KEY")
                if api_key:
                    tmdb_client = TMDBClient(api_key=api_key)
                    # Search for the movie by ID
                    search_results = tmdb_client.search_media(title=str(movie_id))
                    if search_results:
                        movie = search_results[0]
                        # Add to database
                        database.add_media(movie)
                    else:
                        abort(404)
                else:
                    abort(404)
            except Exception as e:
                print(f"Error fetching movie {movie_id}: {e}")
                abort(404)
    
    if movie is None:
        abort(404)
    
    movie = dict(movie)
    
    genre_ids = movie.get("genre_ids", [])
    
    if not genre_ids:
        genre_ids = database.get_movie_genres(movie_id)
    
    movie["genre_names"] = search_client.genre_ids_to_names(genre_ids)
    
    if session.get("user_id") is not None:
        user_movies = database.get_user_movies(session["user_id"])
        user_movie = None
        for um in user_movies:
            if um["id"] == movie["id"]:
                user_movie = um
                break
        try:
            rating = user_movie["rating"]
        except TypeError:
            rating = None
        if user_movie and rating:
            movie["rating"] = rating
    return render_template("movie_detail.html", movie=movie)


@app.route("/movie/<int:movie_id>/videos.json")
def movie_videos_json(movie_id):
    # Try to get the media from current movies list to determine media_type
    global movies
    media = next((m for m in movies if m["id"] == movie_id), None)
    media_type = "movie"  # default
    if media and media.get("media_type"):
        media_type = media["media_type"]
    
    videos = search_client.get_media_videos(movie_id, media_type)
    return {
      "results": [
        {"key": v["key"], "name": v["name"], "type": v["type"]}
        for v in videos
      ]
    }

@app.route("/chat", methods=["GET"])
def chat_page():
    return render_template("chat.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "")
    context = []
    if session.get("user_id"):
        history = get_chat_history(session["user_id"])
        user_data = database.get_user_movies(session["user_id"])
        for user_movie in user_data:
            media = dict(user_movie)
            # Add genre_names for chatbot context
            genre_ids = database.get_movie_genres(media['id'])
            media['genre_names'] = search_client.genre_ids_to_names(genre_ids)
            context.append(media)
        history = get_chat_history(session['user_id'])
    else:
        context = None
        history = []
    history.append({'role': 'user', 'message': user_message})

    response = get_chatbot_response(user_message, context, history)
    cleaned = clean_response(response)

    if session.get('user_id'):
        save_chat_message(session['user_id'], 'user', user_message)
        save_chat_message(session['user_id'], 'assistant', cleaned)

    return jsonify({"response": cleaned})


@app.route("/recommendations")
def recommendations():
    global recommender
    
    if not session.get("user_id"):
        return redirect(url_for("login"))
    
    if recommender is None:
        try:
            recommender = MovieRecommender()
        except Exception as e:
            return render_template("recommendations.html", 
                                 recommendations=[], 
                                 user_name=session.get("username"),
                                 error="Recommendation model not available. Please try again later.")
    
    try:
        # Get personalized recommendations for the user (minimum 5, maximum 10)
        user_recommendations = recommender.recommend_for_user(session["user_id"], top_n=10)
        
        # Log the number of recommendations we got
        print(f"Generated {len(user_recommendations)} recommendations for user")
        if len(user_recommendations) < 5:
            print(f"Note: Got {len(user_recommendations)} recommendations (limited by database size)")
        
        # Add genre information to recommendations
        for rec in user_recommendations:
            genre_ids = database.get_movie_genres(rec['id'])
            rec['genre_names'] = search_client.genre_ids_to_names(genre_ids)
        
        return render_template("recommendations.html", 
                             recommendations=user_recommendations, 
                             user_name=session.get("username"),
                             last_update=session.get("last_model_update"))
    except Exception as e:
        print(f"Error generating recommendations: {e}")
        return render_template("recommendations.html", 
                             recommendations=[], 
                             user_name=session.get("username"),
                             error=f"Error generating recommendations: {str(e)}",
                             last_update=session.get("last_model_update"))

@app.route("/retrain_model", methods=["POST"])
def retrain_model():
    """Retrain the recommendation model with updated data"""
    if not session.get("user_id"):
        return jsonify({"success": False, "error": "Not logged in"})
    
    global recommender
    try:
        # Rebuild the model with current database data
        recommender = MovieRecommender()
        return jsonify({"success": True, "message": "Model retrained successfully"})
    except Exception as e:
        print(f"Error retraining model: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/refresh_recommendations")
def refresh_recommendations():
    """Force refresh recommendations and redirect back"""
    if not session.get("user_id"):
        return redirect(url_for("login"))
    
    global recommender
    try:
        # Force rebuild the model with current database data
        if recommender is None:
            recommender = MovieRecommender()
        else:
            recommender.force_rebuild()
        print("Recommendations refreshed manually")
        # Store the last update time in session
        from datetime import datetime
        session['last_model_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"Error refreshing recommendations: {e}")
    
    return redirect(url_for("recommendations"))

@app.route("/add_popular_movies")
def add_popular_movies():
    """Manually add popular movies to the database"""
    if not session.get("user_id"):
        return redirect(url_for("login"))
    
    try:
        from search import TMDBClient
        import os
        from dotenv import load_dotenv
        
        load_dotenv()
        api_key = os.getenv("TMDB_API_KEY")
        if api_key:
            tmdb_client = TMDBClient(api_key=api_key)
            
            # Search for specific popular movies
            popular_search_terms = ['Avengers', 'Batman', 'Spider-Man', 'Iron Man', 'Captain America', 'Wonder Woman', 'Black Panther', 'Thor']
            added_count = 0
            
            for search_term in popular_search_terms:
                try:
                    search_results = tmdb_client.search_media(title=search_term)
                    for movie in search_results[:2]:  # Get top 2 results for each search
                        # Add to database
                        movie_data = {
                            'id': movie['id'],
                            'title': movie['title'],
                            'overview': movie.get('overview', ''),
                            'vote_average': movie.get('vote_average', 0),
                            'vote_count': movie.get('vote_count', 0),
                            'popularity': movie.get('popularity', 0),
                            'poster_path': movie.get('poster_path', ''),
                            'media_type': movie.get('media_type', 'movie')
                        }
                        database.add_media(movie_data)
                        added_count += 1
                except Exception as e:
                    print(f"Error searching for {search_term}: {e}")
            
            print(f"Added {added_count} popular movies to database")
            
            # Rebuild the recommendation model
            global recommender
            if recommender:
                recommender.force_rebuild()
            
            # Store the last update time in session
            from datetime import datetime
            session['last_model_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
    except Exception as e:
        print(f"Error adding popular movies: {e}")
    
    return redirect(url_for("recommendations"))

def refresh_model():
    """Refresh the recommendation model - called when new movies are added"""
    global recommender
    try:
        if recommender is None:
            recommender = MovieRecommender()
        else:
            recommender.force_rebuild()
        print("Recommendation model refreshed successfully")
        # Store the last update time in session
        from datetime import datetime
        session['last_model_update'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"Error refreshing recommendation model: {e}")

if __name__ == "__main__":
    app.run(debug=True)