# app.py
"""
Flask app for facial emotion recognition with optional Spotify song tracking.
"""

import os
from flask import Flask, render_template, Response, jsonify, redirect, url_for
from supabase_client import get_supabase
from dotenv import load_dotenv
from auth import AuthManager
from camera import CameraManager
from music import MusicManager

# Load environment variables
load_dotenv()

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev')

# Initialize managers
auth_manager = AuthManager()
camera_manager = CameraManager()
music_manager = MusicManager()

# Determine Spotify config
SPOTIFY_CONFIGURED = any([
    os.getenv("SPOTIFY_CLIENT_ID"),
    os.getenv("SPOTIPY_CLIENT_ID")
])

# Routes
@app.route('/login')
def login():
    return auth_manager.login()

@app.route('/callback')
def spotify_callback():
    return auth_manager.spotify_callback()

@app.route('/logout')
def logout():
    return auth_manager.logout()

@app.route('/')
def index():
    user = auth_manager.get_current_user()
    return render_template('index.html', user=user, spotify_configured=SPOTIFY_CONFIGURED)

@app.route('/camera/toggle', methods=['POST'])
def toggle_camera():
    if camera_manager.camera_initializing:
        return jsonify({"status": "error", "message": "Camera initializing"}), 500
    
    success, message = camera_manager.toggle_camera()
    
    if success:
        return jsonify({"status": "success", "camera_active": camera_manager.camera_active})
    else:
        return jsonify({"status": "error", "message": message}), 500

@app.route('/current_song')
def current_song():
    user = auth_manager.get_current_user()
    return music_manager.get_current_song(user)

@app.route('/video_feed')
def video_feed():
    user = auth_manager.get_current_user()
    return Response(
        camera_manager.generate_video(user), 
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/dashboard')
def dashboard():
    user = auth_manager.get_current_user()
    if not user:
        return redirect(url_for('login'))
    supabase = get_supabase()
    try:
        res = supabase.table('song_emotions').select('song_name,artist_name,emotion,song_id').eq('user_id', user['id']).execute()
        rows = res.data or []
    except Exception as e:
        print(f"[dashboard] error fetching song_emotions: {e}")
        rows = []
    return render_template('dashboard.html', user=user, rows=rows)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 8888)))
