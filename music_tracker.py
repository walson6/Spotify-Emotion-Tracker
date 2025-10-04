# music_tracker.py
import os
from datetime import datetime
from typing import Optional
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from models import SpotifyToken
from dotenv import load_dotenv

# Load environment variables early in this module too
load_dotenv()

class MusicTracker:
    def __init__(self, user_id: Optional[int] = None):
        self.user_id = user_id

    @staticmethod
    def _env_names():
        # Support either SPOTIFY_* or SPOTIPY_* names (backwards-compat)
        client = os.getenv("SPOTIFY_CLIENT_ID") or os.getenv("SPOTIPY_CLIENT_ID")
        secret = os.getenv("SPOTIFY_CLIENT_SECRET") or os.getenv("SPOTIPY_CLIENT_SECRET")
        redirect = os.getenv("SPOTIFY_REDIRECT_URI") or os.getenv("SPOTIPY_REDIRECT_URI")
        return client, secret, redirect

    @staticmethod
    def create_spotify_oauth():
        return SpotifyOAuth(
            client_id=os.getenv("SPOTIPY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
            redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
            scope="user-read-playback-state user-read-currently-playing user-read-email"
        )

    @staticmethod
    def get_token(user_id: int) -> Optional[str]:
        if not user_id:
            return None
        token = SpotifyToken.get_by_user_id(user_id)
        if not token:
            return None

        # If expired, refresh
        if token.is_expired():
            spotify_oauth = MusicTracker.create_spotify_oauth()
            if spotify_oauth is None:
                print("[MusicTracker] Cannot refresh token: Spotify OAuth not configured.")
                return None
            try:
                token_info = spotify_oauth.refresh_access_token(token.refresh_token)
                token = SpotifyToken.create_or_update(
                    user_id=user_id,
                    access_token=token_info['access_token'],
                    refresh_token=token_info.get('refresh_token', token.refresh_token),
                    expires_in=token_info.get('expires_in', 3600)
                )
            except Exception as e:
                print(f"[MusicTracker] Error refreshing token: {e}")
                return None

        return token.access_token

    @staticmethod
    def get_current_song(user_id: int) -> dict:
        if not user_id:
            return {"name": "N/A", "artist": "N/A", "id": None}
        access_token = MusicTracker.get_token(user_id)
        if not access_token:
            return {"name": "N/A", "artist": "N/A", "id": None}
        try:
            sp = spotipy.Spotify(auth=access_token)
            current = sp.current_user_playing_track()
            if current and current.get("is_playing") and current.get("item"):
                item = current["item"]
                return {
                    "name": item.get("name", "N/A"),
                    "artist": item.get("artists", [{"name": "N/A"}])[0].get("name", "N/A"),
                    "id": item.get("id")
                }
        except Exception as e:
            print(f"[MusicTracker] Error fetching current song: {e}")
        return {"name": "N/A", "artist": "N/A", "id": None}
