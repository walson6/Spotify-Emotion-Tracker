# music.py
"""
Music module - handles Spotify integration and music-related operations.
"""
from flask import jsonify
from music_tracker import MusicTracker
from typing import Optional, Dict, Any


class MusicManager:
    """Handles all music-related operations."""
    
    def __init__(self):
        pass
    
    def get_current_song(self, user: Optional[Dict[str, Any]]) -> tuple:
        """Get current playing song for the logged-in user."""
        if not user:
            return jsonify({"error": "not_logged_in"}), 401
        
        user_id = user['id']
        try:
            song = MusicTracker.get_current_song(user_id)
            if not song or not isinstance(song, dict):
                return jsonify({"song": "N/A", "artist": "N/A", "id": None})
            
            return jsonify({
                "song": song.get("name", "N/A"),
                "artist": song.get("artist", "N/A"),
                "id": song.get("id", None)
            })
        except Exception as e:
            print(f"[MusicManager] Error: {e}")
            return jsonify({"song": "N/A", "artist": "N/A", "id": None})
