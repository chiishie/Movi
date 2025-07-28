import sqlite3

class MovieRankerDB:
    def __init__(self, db_path='movie_ranker.db'):
        self.init_db()

    def db_connect(self):
        conn = sqlite3.connect('movie_ranker.db')
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self.db_connect()
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            password TEXT NOT NULL
        )
        """)

        # Movies table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY,
            backdrop_path TEXT,
            poster_path TEXT,
            original_language TEXT,
            title TEXT NOT NULL,
            overview TEXT,
            release_date TEXT,
            vote_average REAL,
            vote_count INTEGER,
            popularity REAL,
            media_type TEXT NOT NULL
        )
        """)

        # User_Movies table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_movies (
            user_id INTEGER,
            movie_id INTEGER,
            rating REAL NOT NULL,
            PRIMARY KEY (user_id, movie_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (movie_id) REFERENCES movies(id)
        )
        """)

        # Genre_Map table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS genre_map (
            movie_id INTEGER,
            genre_id INTEGER,
            PRIMARY KEY (movie_id, genre_id),
            FOREIGN KEY (movie_id) REFERENCES movies(id)
        )
        """)

        # Chat History table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            session_id TEXT,
            role TEXT NOT NULL,
            message TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """)

        conn.commit()
        conn.close()

    def add_media(self, media_data):
        conn = self.db_connect()
        cursor = conn.cursor()
        media_type = media_data.get('media_type', 'movie')
        is_movie = media_type == 'movie'
        title = media_data['title'] if is_movie else media_data['name']
        
        # Safely get release date with fallback
        release_date = None
        if is_movie:
            release_date = media_data.get('release_date')
        else:
            release_date = media_data.get('first_air_date')
        
        media_data = dict(media_data) 
        self.add_genres(media_data['id'], media_data.get('genre_ids', []))
        cursor.execute("""
        INSERT OR IGNORE INTO movies (id, backdrop_path, poster_path, original_language, title, overview, release_date, vote_average, vote_count, popularity, media_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            media_data['id'], media_data.get('backdrop_path'),
            media_data.get('poster_path'), media_data.get('original_language', 'en'), title,
            media_data.get('overview'), release_date, media_data.get('vote_average', 0),
            media_data.get('vote_count', 0), media_data.get('popularity', 0), media_type
        ))
        conn.commit()
        conn.close()


    def add_user(self, username, password):
        with self.db_connect() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO users (name, password) VALUES (?, ?)', (username, password))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                print(f"User {username} already exists")
                return False


    def get_user_by_username(self, username):
        conn = self.db_connect()
        with self.db_connect() as conn:
            cursor = conn.cursor()
            user = cursor.execute("SELECT * FROM users WHERE name = ?", (username,)).fetchone()
            if user is None:
                print(f"User {username} does not exist")
                return None
            else:
                return user
            
    def add_user_movies_by_id(self, user_id, movie_id, rating):
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO user_movies (user_id, movie_id, rating)
        VALUES (?, ?, ?)
        """, (user_id, movie_id, rating))
        conn.commit()
        conn.close()

    def add_user_movies_by_name(self, user_name, movie_id, rating):
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO user_movies (user_id, movie_id, rating)
        VALUES ((SELECT id FROM users WHERE name = ?), ?, ?)
        """, (user_name, movie_id, rating))
        conn.commit()
        conn.close()

    def add_genre(self, movie_id, genre_id):
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR IGNORE INTO genre_map (movie_id, genre_id)
        VALUES (?, ?)
        """, (movie_id, genre_id))
        conn.commit()
        conn.close()

    def add_genres(self, movie_id, genre_ids):
        conn = self.db_connect()
        cursor = conn.cursor()
        for genre_id in genre_ids:
            self.add_genre(movie_id, genre_id)
        conn.close()

    def get_user_movies(self, id, sort_by="rating", ascending=False):
        conn = self.db_connect()
        cursor = conn.cursor()
        sort_fields = {
            "rating": "um.rating",
            "popularity": "m.popularity",
            "title": "m.title",
            "vote_average": "m.vote_average",
            "vote_count": "m.vote_count",
            "release_date": "m.release_date"
        }

        sort_column = sort_fields.get(sort_by)
        if not sort_column:
            raise ValueError(f"Invalid sort field '{sort_by}'. Must be one of: {', '.join(sort_fields)}")

        order = "ASC" if ascending else "DESC"
        cursor.execute(f"""
            SELECT m.*, um.rating
            FROM users u
            JOIN user_movies um ON u.id = um.user_id
            JOIN movies m ON um.movie_id = m.id
            WHERE u.id = ?
            ORDER BY {sort_column} {order}
        """, (id,))
        results = cursor.fetchall()
        conn.close()
        print(results)
        return results
        
    def get_movie_data(self, movie_id):
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
        result = cursor.fetchone()
        conn.close()
        return result

    def rm_user_by_name(self, user_name):
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE name = ?", (user_name,))
        conn.commit()
        conn.close()

    def rm_user_by_id(self, user_id):
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()

    def rm_user_movie_by_name(self, user_name, movie_id):
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("""
        DELETE FROM user_movies
        WHERE user_id = (SELECT id FROM users WHERE name = ?) AND movie_id = ?
        """, (user_name, movie_id))
        conn.commit()
        conn.close()

    def rm_user_movie_by_id(self, user_id, movie_id):
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("""
        DELETE FROM user_movies
        WHERE user_id = ? AND movie_id = ?
        """, (user_id, movie_id))
        conn.commit()
        conn.close()

    def rm_movie(self, movie_id):
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM movies WHERE id = ?", (movie_id,))
        conn.commit()
        conn.close()

    def get_movie_genres(self, movie_id):
        '''Get genre IDs for a specific movie from the genre_map table.'''
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("SELECT genre_id FROM genre_map WHERE movie_id = ?", (movie_id,))
        results = cursor.fetchall()
        conn.close()
        return [row['genre_id'] for row in results]

    # Debug methods
    def print_all_users(self):
        '''Prints all users to the console.'''
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        print("All Users:")
        for user in users:
            print(f"User ID: {user['id']}, Name: {user['name']}")
        conn.close()

    def print_all_movies(self):
        '''Prints all movies to the console.'''
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM movies")
        movies = cursor.fetchall()
        print("All Movies:")
        for movie in movies:
            print(f"Movie ID: {movie['id']}, Title: {movie['title']}, Rating: {movie['vote_average']}")
        conn.close()

    def print_all_user_movies(self, user_name):
        '''Prints all movies for a specific user to the console.'''
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.*, um.rating
            FROM users u
            JOIN user_movies um ON u.id = um.user_id
            JOIN movies m ON um.movie_id = m.id
            WHERE u.name = ?
        """, (user_name,))
        user_movies = cursor.fetchall()
        print(f"Movies for user '{user_name}':")
        for movie in user_movies:
            print(f"Movie ID: {movie['id']}, Title: {movie['title']}, Rating: {movie['rating']}")
        conn.close()

    def clear_database(self):
        '''Clears all data from the database.'''
        conn = self.db_connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM user_movies")
        cursor.execute("DELETE FROM genre_map")
        cursor.execute("DELETE FROM movies")
        cursor.execute("DELETE FROM users")
        conn.commit()
        conn.close()
