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


app = Flask(__name__)
app.secret_key = os.urandom(24)
load_dotenv()

search_client = None
movies = []


# Run once at the start to fetch data from TMDB API
def init_app():
    global search_client, database

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

@app.route("/")
def search():
    global movies
    query = request.args.get('query')
    if query:
        movies = search_client.search_movies(title=query)
        return render_template("search.html", movies=movies, query=query,is_discover=False)
    else:
        page = request.args.get('page', 1, type=int)
        movies = search_client.discover_movies(page=page)
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
    movies = database.get_user_movies(session.get("user_id"))
    return render_template("my_movies.html", movies=movies, user_name=session.get("username"))

@app.route("/rate_movie/<int:movie_id>", methods=["POST"])
def rate_movie(movie_id):
    rating = request.form.get("rating")
    if rating and session.get("user_id") is not None:
        print(f"id: {session['user_id']}, movie_id: {movie_id}, rating: {rating}")
        global movies
        movie = next((m for m in movies if m["id"] == movie_id), None)
        database.add_movie(movie)
        database.add_user_movies_by_id(session["user_id"], movie_id, rating)
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
    if movie is None:
        abort(404)
    movie = dict(movie)
    movie["genre_names"] = search_client.genre_ids_to_names(movie.get("genre_ids", []))
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
    videos = search_client.get_movie_videos(movie_id)
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
    response = get_chatbot_response(user_message)
    cleaned= clean_response(response)
    return jsonify({"response": cleaned})

if __name__ == "__main__":
    app.run(debug=True)