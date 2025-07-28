import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import sqlite3
import joblib

class MovieRecommender:
    def __init__(self, db_path='movie_ranker.db'):
        self.db_path = db_path
        self.vectorizer = None
        self.tfidf_matrix = None
        self.title_to_index = None
        self.similarity_matrix = None
        self.movies_df = None
        self._build_model()
    
    def _build_model(self):
        """Build the recommendation model from database data"""
        print("Building recommendation model from fresh database data...")
        # Get movies from database
        conn = sqlite3.connect(self.db_path)
        query = """
        SELECT id, title, overview, vote_average, vote_count, popularity, poster_path
        FROM movies 
        WHERE overview IS NOT NULL AND title IS NOT NULL
        """
        self.movies_df = pd.read_sql_query(query, conn)
        conn.close()
        
        if self.movies_df.empty:
            print("No movies found in database. Please add some movies first.")
            return
        
        print(f"Loaded {len(self.movies_df)} movies from database")
        
        # Create content for vectorization
        self.movies_df['content'] = self.movies_df['title'] + ' ' + self.movies_df['overview'].fillna('')
        
        # Create TF-IDF vectors
        self.vectorizer = TfidfVectorizer(stop_words='english', max_features=5000)
        self.tfidf_matrix = self.vectorizer.fit_transform(self.movies_df['content'])
        
        # Create title to index mapping
        self.title_to_index = pd.Series(self.movies_df.index, index=self.movies_df['title']).drop_duplicates()
        
        # Calculate similarity matrix
        self.similarity_matrix = cosine_similarity(self.tfidf_matrix)
        print("Model built successfully!")
    
    def get_user_rated_movies(self, user_id):
        """Get movies rated by a specific user"""
        conn = sqlite3.connect(self.db_path)
        query = """
        SELECT m.id, m.title, m.overview, um.rating, m.vote_average, m.vote_count, m.popularity, m.poster_path
        FROM movies m
        JOIN user_movies um ON m.id = um.movie_id
        WHERE um.user_id = ? AND um.rating >= 3.0
        ORDER BY um.rating DESC
        """
        user_movies = pd.read_sql_query(query, conn, params=(user_id,))
        conn.close()
        return user_movies
    
    def get_user_all_rated_movies(self, user_id):
        """Get ALL movies rated by a specific user (including low ratings)"""
        conn = sqlite3.connect(self.db_path)
        query = """
        SELECT m.id, m.title, m.overview, um.rating, m.vote_average, m.vote_count, m.popularity, m.poster_path
        FROM movies m
        JOIN user_movies um ON m.id = um.movie_id
        WHERE um.user_id = ?
        ORDER BY um.rating DESC
        """
        user_movies = pd.read_sql_query(query, conn, params=(user_id,))
        conn.close()
        return user_movies
    
    def recommend_for_user(self, user_id, top_n=10, random_seed=None):
        """Generate recommendations for a specific user based on their ratings"""
        print(f"Debug: Getting recommendations for user {user_id}")
        user_movies = self.get_user_rated_movies(user_id)
        print(f"Debug: Found {len(user_movies)} rated movies for user")
        
        # Get ALL movies the user has rated (to exclude them from recommendations)
        all_rated_movies = self.get_user_all_rated_movies(user_id)
        rated_movie_ids = set(all_rated_movies['id'].tolist())
        print(f"Debug: User has rated {len(rated_movie_ids)} movies total (to exclude from recommendations)")
        
        if user_movies.empty:
            print("Debug: User has no ratings, returning popular movies")
            # If user has no ratings, return popular movies
            popular = self.get_popular_movies(top_n, random_seed=random_seed)
            print(f"Debug: Returning {len(popular)} popular movies")
            return popular
        
        # Get titles of user's highly rated movies
        user_titles = user_movies['title'].tolist()
        print(f"Debug: User's highly rated movies: {user_titles}")
        
        # Get recommendations based on user's movies
        recommendations = self.recommend(user_titles, top_n, rated_movie_ids, random_seed=random_seed)
        print(f"Debug: Generated {len(recommendations)} recommendations")
        
        # If we don't have enough recommendations, add popular movies (excluding rated)
        if len(recommendations) < top_n:
            print(f"Debug: Only got {len(recommendations)} recommendations, adding popular movies")
            popular_movies = self.get_popular_movies(top_n * 2, rated_movie_ids, random_seed=random_seed)  # Get more popular movies, excluding rated
            
            # Filter out movies that are already in recommendations
            existing_ids = {rec['id'] for rec in recommendations}
            new_popular = [movie for movie in popular_movies if movie['id'] not in existing_ids]
            
            # Add enough to reach top_n
            needed = top_n - len(recommendations)
            recommendations.extend(new_popular[:needed])
            print(f"Debug: Added {min(needed, len(new_popular))} popular movies, total: {len(recommendations)}")
        
        # If still not enough recommendations, fetch popular movies from TMDB API
        if len(recommendations) < top_n:
            print(f"Debug: Still only got {len(recommendations)} recommendations, fetching from TMDB API")
            try:
                from search import TMDBClient
                import os
                from dotenv import load_dotenv
                
                load_dotenv()
                api_key = os.getenv("TMDB_API_KEY")
                if api_key:
                    tmdb_client = TMDBClient(api_key=api_key)
                    # Fetch popular movies from TMDB
                    tmdb_movies = tmdb_client.discover_movies(page=1)
                    
                    # Filter out movies already in database and user's rated movies
                    existing_ids = {rec['id'] for rec in recommendations}
                    new_tmdb_movies = []
                    
                    for movie in tmdb_movies:
                        if movie['id'] not in existing_ids and movie['id'] not in rated_movie_ids:
                            # Convert TMDB format to our format
                            new_movie = {
                                'id': movie['id'],
                                'title': movie['title'],
                                'overview': movie.get('overview', ''),
                                'vote_average': movie.get('vote_average', 0),
                                'vote_count': movie.get('vote_count', 0),
                                'popularity': movie.get('popularity', 0),
                                'poster_path': movie.get('poster_path', '')
                            }
                            new_tmdb_movies.append(new_movie)
                    
                    # Add enough to reach top_n
                    needed = top_n - len(recommendations)
                    recommendations.extend(new_tmdb_movies[:needed])
                    print(f"Debug: Added {min(needed, len(new_tmdb_movies))} TMDB movies, total: {len(recommendations)}")
                    
                    # Add these movies to the database for future use
                    import database
                    db = database.MovieRankerDB()
                    for movie in new_tmdb_movies[:needed]:
                        movie_data = {
                            'id': movie['id'],
                            'title': movie['title'],
                            'overview': movie['overview'],
                            'vote_average': movie['vote_average'],
                            'vote_count': movie['vote_count'],
                            'popularity': movie['popularity'],
                            'poster_path': movie['poster_path'],
                            'release_date': movie.get('release_date'),
                            'original_language': movie.get('original_language', 'en'),
                            'media_type': 'movie'
                        }
                        db.add_media(movie_data)
                    print(f"Debug: Added {min(needed, len(new_tmdb_movies))} movies to database")
                    
                    # Also search for specific popular movies like Avengers and Batman
                    popular_search_terms = ['Avengers', 'Batman', 'Spider-Man', 'Iron Man', 'Captain America', 'Wonder Woman']
                    for search_term in popular_search_terms:
                        try:
                            search_results = tmdb_client.search_media(title=search_term)
                            for movie in search_results[:2]:  # Get top 2 results for each search
                                if movie['id'] not in existing_ids and movie['id'] not in rated_movie_ids:
                                    # Convert TMDB format to our format
                                    new_movie = {
                                        'id': movie['id'],
                                        'title': movie['title'],
                                        'overview': movie.get('overview', ''),
                                        'vote_average': movie.get('vote_average', 0),
                                        'vote_count': movie.get('vote_count', 0),
                                        'popularity': movie.get('popularity', 0),
                                        'poster_path': movie.get('poster_path', ''),
                                        'media_type': movie.get('media_type', 'movie')
                                    }
                                    
                                    # Add to recommendations if we still need more
                                    if len(recommendations) < top_n:
                                        recommendations.append(new_movie)
                                        existing_ids.add(movie['id'])
                                    
                                    # Add to database
                                    movie_data = {
                                        'id': movie['id'],
                                        'title': movie['title'],
                                        'overview': movie.get('overview', ''),
                                        'vote_average': movie.get('vote_average', 0),
                                        'vote_count': movie.get('vote_count', 0),
                                        'popularity': movie.get('popularity', 0),
                                        'poster_path': movie.get('poster_path', ''),
                                        'release_date': movie.get('release_date'),
                                        'original_language': movie.get('original_language', 'en'),
                                        'media_type': movie.get('media_type', 'movie')
                                    }
                                    db.add_media(movie_data)
                        except Exception as e:
                            print(f"Debug: Error searching for {search_term}: {e}")
                    
                    print(f"Debug: Final recommendations after adding popular movies: {len(recommendations)}")
                    
                    # Ensure all recommended movies are in the database
                    self._ensure_movies_in_database(recommendations)
                    
                    # Also search for specific popular movies like Avengers and Batman
                    popular_search_terms = ['Avengers', 'Batman', 'Spider-Man', 'Iron Man', 'Captain America', 'Wonder Woman']
                    for search_term in popular_search_terms:
                        try:
                            search_results = tmdb_client.search_media(title=search_term)
                            for movie in search_results[:2]:  # Get top 2 results for each search
                                if movie['id'] not in existing_ids and movie['id'] not in rated_movie_ids:
                                    # Convert TMDB format to our format
                                    new_movie = {
                                        'id': movie['id'],
                                        'title': movie['title'],
                                        'overview': movie.get('overview', ''),
                                        'vote_average': movie.get('vote_average', 0),
                                        'vote_count': movie.get('vote_count', 0),
                                        'popularity': movie.get('popularity', 0),
                                        'poster_path': movie.get('poster_path', ''),
                                        'media_type': movie.get('media_type', 'movie')
                                    }
                                    
                                    # Add to recommendations if we still need more
                                    if len(recommendations) < top_n:
                                        recommendations.append(new_movie)
                                        existing_ids.add(movie['id'])
                                    
                                    # Add to database
                                    movie_data = {
                                        'id': movie['id'],
                                        'title': movie['title'],
                                        'overview': movie.get('overview', ''),
                                        'vote_average': movie.get('vote_average', 0),
                                        'vote_count': movie.get('vote_count', 0),
                                        'popularity': movie.get('popularity', 0),
                                        'poster_path': movie.get('poster_path', ''),
                                        'release_date': movie.get('release_date'),
                                        'original_language': movie.get('original_language', 'en'),
                                        'media_type': movie.get('media_type', 'movie')
                                    }
                                    db.add_media(movie_data)
                        except Exception as e:
                            print(f"Debug: Error searching for {search_term}: {e}")
                    
                    print(f"Debug: Final recommendations after adding popular movies: {len(recommendations)}")
                    
            except Exception as e:
                print(f"Debug: Error fetching from TMDB API: {e}")
        
        # Final check: if we have fewer than requested, that's okay (limited database)
        if len(recommendations) < top_n:
            print(f"Debug: Final result: {len(recommendations)} movies (database has limited movies)")
        
        return recommendations  # Return all available movies (up to top_n)
    
    def recommend(self, saved_titles, top_n=5, exclude_movie_ids=None, random_seed=None):
        """Recommend movies based on a list of movie titles"""
        if self.similarity_matrix is None:
            print("Debug: No similarity matrix available")
            return []
        
        # Find indices of the input movies
        indices = []
        for title in saved_titles:
            if title in self.title_to_index:
                indices.append(self.title_to_index[title])
        
        print(f"Debug: Found {len(indices)} movies in similarity matrix")
        
        if not indices:
            print("Debug: No matching movies found in similarity matrix")
            return []

        # Calculate average similarity scores
        avg_scores = sum(self.similarity_matrix[i] for i in indices) / len(indices)
        
        # Get top similar movies (excluding the input movies AND user's rated movies)
        ranked = sorted(list(enumerate(avg_scores)), key=lambda x: x[1], reverse=True)
        
        # Filter out both input movies and user's rated movies
        if exclude_movie_ids:
            all_candidates = []
            for idx, score in ranked:
                if idx not in indices:
                    # Get the movie ID for this index
                    movie_id = self.movies_df.iloc[idx]['id']
                    if movie_id not in exclude_movie_ids:
                        all_candidates.append(idx)
        else:
            all_candidates = [i for i, score in ranked if i not in indices]
        
        print(f"Debug: Found {len(all_candidates)} candidate movies (excluding rated)")
        
        # If no unrated candidates, we can't recommend anything (don't include rated movies)
        if not all_candidates:
            print("Debug: No unrated candidates available - user has rated all similar movies")
            return []
        
        # Get more candidates than needed for randomization
        recommendations = all_candidates[:min(top_n * 3, len(all_candidates))]
        
        # Add some randomization to ensure variety
        import random
        if random_seed:
            random.seed(random_seed)
        if len(recommendations) > top_n:
            recommendations = random.sample(recommendations, min(top_n, len(recommendations)))
        
        print(f"Debug: Selected {len(recommendations)} movies for recommendations")
        
        # Return recommended movies with additional info
        recommended_movies = self.movies_df.iloc[recommendations][['id', 'title', 'overview', 'vote_average', 'vote_count', 'popularity', 'poster_path']]
        return recommended_movies.to_dict(orient='records')
    
    def get_popular_movies(self, top_n=10, exclude_movie_ids=None, random_seed=None):
        """Get popular movies based on vote_average and vote_count"""
        print(f"Debug: Getting {top_n} popular movies")
        if self.movies_df is None or self.movies_df.empty:
            print("Debug: No movies dataframe available")
            return []
        
        print(f"Debug: Movies dataframe has {len(self.movies_df)} movies")
        
        # Calculate popularity score
        self.movies_df['popularity_score'] = (
            self.movies_df['vote_average'] * self.movies_df['vote_count'] * 
            self.movies_df['popularity']
        )
        
        # Filter out user's rated movies if provided
        if exclude_movie_ids:
            available_movies = self.movies_df[~self.movies_df['id'].isin(exclude_movie_ids)]
            print(f"Debug: After excluding rated movies, {len(available_movies)} movies available")
        else:
            available_movies = self.movies_df
        
        # Get top popular movies with some randomization
        popular_movies = available_movies.nlargest(top_n * 2, 'popularity_score')  # Get more movies
        # Randomly sample from top movies to add variety
        import random
        if random_seed:
            random.seed(random_seed)
        if len(popular_movies) > top_n:
            popular_movies = popular_movies.sample(n=top_n, random_state=random.randint(1, 1000))
        
        result = popular_movies[['id', 'title', 'overview', 'vote_average', 'vote_count', 'popularity', 'poster_path']].to_dict(orient='records')
        print(f"Debug: Returning {len(result)} popular movies")
        return result
    
    def force_rebuild(self):
        """Force a complete rebuild of the model"""
        print("Force rebuilding recommendation model...")
        self._build_model()
        print("Model force rebuild completed!")
    
    def get_fresh_recommendations(self, user_id, top_n=10):
        """Generate fresh recommendations with new randomization"""
        import random
        import time
        
        # Generate a new random seed based on current time and user ID
        random_seed = int(time.time() * 1000) + user_id + random.randint(1, 10000)
        print(f"Debug: Generating fresh recommendations with random seed: {random_seed}")
        
        return self.recommend_for_user(user_id, top_n, random_seed=random_seed)
    
    def _ensure_movies_in_database(self, recommendations):
        """Ensure all recommended movies are properly added to the database"""
        import database
        db = database.MovieRankerDB()
        
        for movie in recommendations:
            try:
                # Check if movie exists in database
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM movies WHERE id = ?", (movie['id'],))
                exists = cursor.fetchone()
                conn.close()
                
                if not exists:
                    # Add movie to database
                    movie_data = {
                        'id': movie['id'],
                        'title': movie['title'],
                        'overview': movie.get('overview', ''),
                        'vote_average': movie.get('vote_average', 0),
                        'vote_count': movie.get('vote_count', 0),
                        'popularity': movie.get('popularity', 0),
                        'poster_path': movie.get('poster_path', ''),
                        'release_date': movie.get('release_date'),
                        'original_language': movie.get('original_language', 'en'),
                        'media_type': movie.get('media_type', 'movie')
                    }
                    db.add_media(movie_data)
                    print(f"Debug: Added movie {movie['title']} to database")
            except Exception as e:
                print(f"Debug: Error ensuring movie {movie.get('title', 'Unknown')} in database: {e}")
    
    def save_model(self, filepath='movie_recommender.pkl'):
        """Save the trained model"""
        model_data = {
            'vectorizer': self.vectorizer,
            'tfidf_matrix': self.tfidf_matrix,
            'title_to_index': self.title_to_index,
            'similarity_matrix': self.similarity_matrix,
            'movies_df': self.movies_df
        }
        joblib.dump(model_data, filepath)
    
    def load_model(self, filepath='movie_recommender.pkl'):
        """Load a trained model"""
        try:
            model_data = joblib.load(filepath)
            self.vectorizer = model_data['vectorizer']
            self.tfidf_matrix = model_data['tfidf_matrix']
            self.title_to_index = model_data['title_to_index']
            self.similarity_matrix = model_data['similarity_matrix']
            self.movies_df = model_data['movies_df']
            return True
        except FileNotFoundError:
            print(f"Model file {filepath} not found. Building new model...")
            self._build_model()
            return False

# Example usage and model training
if __name__ == "__main__":
    # Create and train the model
    recommender = MovieRecommender()
    
    # Save the model
    recommender.save_model()
    
    # Test recommendations
    test_recommendations = recommender.get_popular_movies(5)
    print("Popular movies:", test_recommendations)

