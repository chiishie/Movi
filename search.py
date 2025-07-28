import requests
import json
from urllib.parse import quote
from dotenv import load_dotenv
import os


class TMDBClient:
    def __init__(self, api_key=None, language="en-US", include_adult=False):
        # Get API key
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("TMDB_API_KEY not found.")
        
        self.language = language
        self.include_adult = str(include_adult).lower()
        self.base_url = "https://api.themoviedb.org/3"
        # Remove Bearer token, use simple headers
        self.headers = {
            "accept": "application/json"
        }
        self.fetch_genres()


    def _make_request(self, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"
        if params is None:
            params = {}
        params['api_key'] = self.api_key
    
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            return None


    def search_media(self, title, year=None, page=1, get_all_pages=False, max_results=1000):
        '''Used TMDB's search endpoint to find movies by title.'''
        params = {
        "query": title,
        "page": page,
        "language": self.language,
        "include_adult": self.include_adult
        }
        data = self._make_request("/search/multi", params=params)
    
        if not data or 'results' not in data:
            return []
        results = [
            item for item in data['results'] 
            if item.get('media_type') in ['movie', 'tv']
        ]

    
        for item in results:
            if item.get('media_type') == 'tv':
                item['title'] = item.get('name')
    
        return results


    def discover_movies(self, sort_by="popularity.desc", page=1):
        '''Used TMDB's discover endpoint to get a list of current popular movies.'''
        params = {
            "page": page,
            "language": self.language,
        }
        data = self._make_request("/discover/movie", params=params)
        if not data or 'results' not in data:
            return []
        
        for item in data["results"]:
            item['media_type'] = 'movie'
        
        return data["results"]
    
    def discover_tv_shows(self, sort_by="popularity.desc", page=1):
        '''Used TMDB's discover endpoint to get a list of current popular tv shows.'''
        params = {
            "page": page,
            "language": self.language,
        }
        data = self._make_request("/discover/tv", params=params)
        for item in data["results"]:
            item['media_type'] = 'tv'
        
        return data["results"]


    def discover_mixed_media(self, page=1):
        '''Fetches both popular movies and TV shows, combines and sorts them by popularity.'''
        
        movies = self.discover_movies(page=page)
        tv_shows = self.discover_tv_shows(page=page)
        
        
        for tv_show in tv_shows:
            tv_show['title'] = tv_show.get('name', '')
        
        
        combined_media = movies + tv_shows
        
        combined_media.sort(key=lambda x: x.get('popularity', 0), reverse=True)
        
        return combined_media


    def fetch_genres(self):
        '''Fetches the list of movie and TV genres from TMDB and stores them in dictionaries.'''
     
        movie_url = f"{self.base_url}/genre/movie/list?api_key={self.api_key}&language={self.language}"
        movie_response = requests.get(movie_url, headers=self.headers)
        
    
        tv_url = f"{self.base_url}/genre/tv/list?api_key={self.api_key}&language={self.language}"
        tv_response = requests.get(tv_url, headers=self.headers)
        
        self.movie_genre_map = {}
        self.tv_genre_map = {}
        self.genre_map = {}  

        if movie_response.status_code == 200:
            data = movie_response.json()
            self.movie_genre_map = {genre['id']: genre['name'] for genre in data.get('genres', [])}
            self.genre_map.update(self.movie_genre_map)
        else:
            print(f"Error fetching movie genres: {movie_response.status_code}")

        if tv_response.status_code == 200:
            data = tv_response.json()
            self.tv_genre_map = {genre['id']: genre['name'] for genre in data.get('genres', [])}
            self.genre_map.update(self.tv_genre_map)
        else:
            print(f"Error fetching TV genres: {tv_response.status_code}")


    def genre_ids_to_names(self, genre_ids):
        '''Convert a list of genre IDs to their names using the combined genre_map.'''
        if not hasattr(self, 'genre_map'):
            self.fetch_genres()
        return [self.genre_map.get(genre_id, "Unknown") for genre_id in genre_ids]


    def save_to_file(self, results, filename="movies.json"):
        '''The intent of this function is to serve as a debug tool to save on API calls.'''
        with open(filename, "w") as file:
            json.dump(results, file, indent=2)
        print(f"Saved {len(results)} results to {filename}")
    
    def get_media_videos(self, media_id: int, media_type: str = "movie") -> list[dict]:
        """
        Fetch YouTube video data (trailers, teasers, etc.) for a specific movie or TV show
        from TMDb, then sort by our type preference.
        """
        endpoint = f"/{media_type}/{media_id}/videos"
        url = f"{self.base_url}{endpoint}"
        params = {"api_key": self.api_key, "language": self.language}
        resp = requests.get(url, headers=self.headers, params=params)
        resp.raise_for_status()

        videos = resp.json().get("results", [])
        # Keep only YouTube
        yt = [v for v in videos if v.get("site") == "YouTube"]

        # Sort: Trailer → Teaser → Clip → Featurette → Other
        priority = {"Trailer": 1, "Teaser": 2, "Clip": 3, "Featurette": 4}
        yt.sort(key=lambda v: priority.get(v.get("type", ""), 99))
        return yt

    def get_movie_videos(self, movie_id: int) -> list[dict]:
        """
        Fetch YouTube video data (trailers, teasers, etc.) for a specific movie
        from TMDb, then sort by our type preference.
        """
        return self.get_media_videos(movie_id, "movie")