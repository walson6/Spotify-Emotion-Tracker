# auth.py
"""
Authentication module - handles user login, logout, and session management.
"""
from flask import render_template, redirect, url_for, session, request, flash
from typing import Optional, Dict, Any
from models import User, SpotifyToken
from music_tracker import MusicTracker
from supabase_client import get_supabase
import spotipy


class AuthManager:
    """Handles all authentication-related operations."""
    
    def __init__(self):
        pass
    
    def get_current_user(self) -> Optional[Dict[str, Any]]:
        """Get current logged-in user."""
        user_id = session.get('user_id')
        if not user_id:
            return None
        
        supabase = get_supabase()
        resp = supabase.table("users").select("*").eq("id", user_id).single().execute()
        return resp.data if resp.data else None
    
    def login(self) -> str:
        """Handle login page rendering."""
        if 'user_id' in session:
            return redirect(url_for('index'))
        
        spotify_oauth = MusicTracker.create_spotify_oauth()
        if spotify_oauth is None:
            return render_template('login.html', auth_url=None, error="Spotify not configured.")
        
        try:
            auth_url = spotify_oauth.get_authorize_url()
        except Exception as e:
            print(f"[AuthManager] Error building auth url: {e}")
            auth_url = None
        
        return render_template('login.html', auth_url=auth_url, error=None)
    
    def spotify_callback(self) -> str:
        """Handle Spotify OAuth callback."""
        spotify_oauth = MusicTracker.create_spotify_oauth()
        if spotify_oauth is None:
            flash("Spotify not configured.")
            return redirect(url_for('login'))
        
        code = request.args.get('code')
        if not code:
            flash("No code in callback.")
            return redirect(url_for('login'))
        
        # Exchange code for token
        try:
            token_info = spotify_oauth.get_access_token(code)
        except Exception as e:
            print(f"[AuthManager] Token exchange error: {e}")
            token_info = None
        
        if not token_info or 'access_token' not in token_info:
            flash("Failed to get Spotify access token.")
            return redirect(url_for('login'))
        
        try:
            sp = spotipy.Spotify(auth=token_info['access_token'])
            spotify_user = sp.current_user()
        except Exception as e:
            print(f"[AuthManager] Error fetching spotify user: {e}")
            spotify_user = None
        
        if not spotify_user or not spotify_user.get('id'):
            flash("Failed to fetch Spotify profile.")
            return redirect(url_for('login'))
        
        # Create or get user
        user = User.get_by_spotify_id(spotify_user['id'])
        if not user:
            user = User.create(
                spotify_id=spotify_user['id'],
                email=spotify_user.get('email'),
                display_name=spotify_user.get('display_name')
            )
        
        if not user:
            flash("Failed to create user.")
            return redirect(url_for('login'))
        
        # Store token in DB
        try:
            SpotifyToken.create_or_update(
                user_id=user.id,
                access_token=token_info['access_token'],
                refresh_token=token_info.get('refresh_token', ''),
                expires_in=token_info.get('expires_in', 3600)
            )
        except Exception as e:
            print(f"[AuthManager] Error storing token: {e}")
        
        session['user_id'] = user.id
        return redirect(url_for('index'))
    
    def logout(self) -> str:
        """Handle user logout."""
        session.clear()
        return redirect(url_for('login'))
