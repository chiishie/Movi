#!/usr/bin/env python3
"""
Test script for the movie recommendation model
"""

import sqlite3
from model import MovieRecommender

def test_model():
    """Test the recommendation model"""
    print("Testing Movie Recommendation Model...")
    
    # Test database connection
    try:
        conn = sqlite3.connect('movie_ranker.db')
        cursor = conn.cursor()
        
        # Check if we have movies in the database
        cursor.execute("SELECT COUNT(*) FROM movies")
        movie_count = cursor.fetchone()[0]
        print(f"Found {movie_count} movies in database")
        
        # Check if we have users
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        print(f"Found {user_count} users in database")
        
        # Check if we have ratings
        cursor.execute("SELECT COUNT(*) FROM user_movies")
        rating_count = cursor.fetchone()[0]
        print(f"Found {rating_count} ratings in database")
        
        conn.close()
        
        if movie_count == 0:
            print("No movies found in database. Please add some movies first.")
            return
        
        # Initialize the model
        print("\nInitializing recommendation model...")
        recommender = MovieRecommender()
        
        # Test popular movies
        print("\nTesting popular movies...")
        popular_movies = recommender.get_popular_movies(5)
        print(f"Found {len(popular_movies)} popular movies:")
        for movie in popular_movies:
            print(f"  - {movie['title']} (Rating: {movie['vote_average']})")
        
        # Test recommendations for a specific user (if any exist)
        if user_count > 0:
            # Reconnect to get user ID
            conn = sqlite3.connect('movie_ranker.db')
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users LIMIT 1")
            user_id = cursor.fetchone()[0]
            conn.close()
            
            print(f"\nTesting recommendations for user {user_id}...")
            user_recommendations = recommender.recommend_for_user(user_id, 5)
            print(f"Found {len(user_recommendations)} recommendations for user:")
            for movie in user_recommendations:
                print(f"  - {movie['title']} (Rating: {movie['vote_average']})")
        
        print("\nModel test completed successfully!")
        
    except Exception as e:
        print(f"Error testing model: {e}")

if __name__ == "__main__":
    test_model() 