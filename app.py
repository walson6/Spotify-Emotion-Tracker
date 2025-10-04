# app.py
"""
Flask app for facial emotion recognition with optional Spotify song tracking.
Logs only the majority emotion per song in Supabase (song_emotions table) once per song.
"""

from flask import Flask, render_template, Response, jsonify, redirect, url_for, session, request, flash
import cv2
from fer import FER
from music_tracker import MusicTracker
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import os
from supabase_client import get_supabase
from dotenv import load_dotenv
from collections import Counter
from models import User, SpotifyToken
from typing import Optional

# Load .env early
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev')

detector = FER()

# Camera globals
camera_active = False
camera_initializing = False
cap: Optional[cv2.VideoCapture] = None

# In-memory tracking for emotion counting and song state:
# Keys are "<user_id>_<song_id>"
emotion_counts: dict = {}
# prev_song per user to detect song changes
prev_song: dict = {}
# store whether we've already persisted the previous song's majority
persisted_songs: set = set()
song_snapshot: dict = {}  # user_id -> {"id": song_id, "name": song_name, "artist": artist_name}


# Determine Spotify config exists (supports either SPOTIFY_* or SPOTIPY_* env names)
SPOTIFY_CONFIGURED = any([
    os.getenv("SPOTIFY_CLIENT_ID"),
    os.getenv("SPOTIPY_CLIENT_ID")
])

def get_current_user():
    user_id = session.get('user_id')
    if not user_id:
        return None
    supabase = get_supabase()
    resp = supabase.table("users").select("*").eq("id", user_id).single().execute()
    return resp.data if resp.data else None


@app.route('/login')
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))

    spotify_oauth = MusicTracker.create_spotify_oauth()
    if spotify_oauth is None:
        # show login page but without spotify button
        return render_template('login.html', auth_url=None, error="Spotify not configured.")
    try:
        auth_url = spotify_oauth.get_authorize_url()
    except Exception as e:
        # defensive: don't crash if Spotify lib behaves differently
        print(f"[login] error building auth url: {e}")
        auth_url = None
    return render_template('login.html', auth_url=auth_url, error=None)


@app.route('/callback')
def spotify_callback():
    spotify_oauth = MusicTracker.create_spotify_oauth()
    if spotify_oauth is None:
        flash("Spotify not configured.")
        return redirect(url_for('login'))

    code = request.args.get('code')
    if not code:
        flash("No code in callback.")
        return redirect(url_for('login'))

    # Exchange code for token; handle failures gracefully
    try:
        token_info = spotify_oauth.get_access_token(code)
    except Exception as e:
        print(f"[callback] token exchange error: {e}")
        token_info = None

    if not token_info or 'access_token' not in token_info:
        flash("Failed to get Spotify access token.")
        return redirect(url_for('login'))

    import spotipy
    try:
        sp = spotipy.Spotify(auth=token_info['access_token'])
        spotify_user = sp.current_user()
    except Exception as e:
        print(f"[callback] error fetching spotify user: {e}")
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
        print(f"[callback] error storing token: {e}")

    session['user_id'] = user.id
    return redirect(url_for('index'))


# --- NEW: endpoint to return current playing song for the logged-in user ---
@app.route('/current_song')
def current_song():
    user = get_current_user()
    if not user:
        return jsonify({"error": "not_logged_in"}), 401

    user_id = user['id']
    try:
        song = MusicTracker.get_current_song(user_id)
        # Ensure stable fields
        if not song or not isinstance(song, dict):
            return jsonify({"song": "N/A", "artist": "N/A", "id": None})
        return jsonify({
            "song": song.get("name", "N/A"),
            "artist": song.get("artist", "N/A"),
            "id": song.get("id", None)
        })
    except Exception as e:
        print(f"[current_song] error: {e}")
        return jsonify({"song": "N/A", "artist": "N/A", "id": None})


@app.route('/logout')
def logout():
    # Clear session then go to login page (explicit)
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
def index():
    user = get_current_user()
    # If spotify not configured, show index but disable Spotify-specific UI
    return render_template('index.html', user=user, spotify_configured=SPOTIFY_CONFIGURED)


# Camera helpers
def init_camera():
    global cap, camera_initializing
    if camera_initializing or cap:
        return False
    camera_initializing = True
    backends = [(cv2.CAP_DSHOW, "DirectShow"), (cv2.CAP_MSMF, "Media Foundation"), (cv2.CAP_ANY, "Any")]
    for backend, _name in backends:
        for idx in range(3):
            try:
                cap = cv2.VideoCapture(idx, backend)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        camera_initializing = False
                        return True
                    cap.release()
                    cap = None
            except Exception:
                if cap:
                    cap.release()
                    cap = None
    camera_initializing = False
    cap = None
    return False

def release_camera():
    global cap
    if cap:
        cap.release()
        cap = None

@app.route('/camera/toggle', methods=['POST'])
def toggle_camera():
    global camera_active
    if camera_initializing:
        return jsonify({"status": "error", "message": "Camera initializing"}), 500
    camera_active = not camera_active
    if camera_active and not init_camera():
        return jsonify({"status": "error", "message": "Failed to start camera"}), 500
    if not camera_active:
        release_camera()
    return jsonify({"status": "success", "camera_active": camera_active})


def draw_text_with_border(img, text, position, font_size=26):
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
    for ox, oy in [(1,1),(-1,-1),(1,-1),(-1,1)]:
        draw.text((position[0]+ox, position[1]+oy), text, font=font, fill=(255,255,255))
    draw.text(position, text, font=font, fill=(0,0,0))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


@app.route('/video_feed')
def video_feed():
    user = get_current_user()
    return Response(generate_video(user), mimetype='multipart/x-mixed-replace; boundary=frame')


def persist_song_emotion(user_id: int, song_id: str, song_name: str, artist_name: str):
    global emotion_counts, persisted_songs
    key = f"{user_id}_{song_id}"
    if key not in emotion_counts:
        return
    counts = emotion_counts[key]
    if not counts:
        return
    most_common_emotion, _ = counts.most_common(1)[0]

    supabase = get_supabase()
    try:
        existing = supabase.table("song_emotions").select("id").eq("user_id", user_id).eq("song_id", song_id).execute()
        if existing.data:
            supabase.table("song_emotions").update({
                "emotion": most_common_emotion,
                "song_name": song_name,
                "artist_name": artist_name
            }).eq("id", existing.data[0]['id']).execute()
        else:
            supabase.table("song_emotions").insert({
                "user_id": user_id,
                "song_id": song_id,
                "song_name": song_name,
                "artist_name": artist_name,
                "emotion": most_common_emotion
            }).execute()
        persisted_songs.add(key)
    except Exception as e:
        print(f"[persist] error writing song_emotions for {key}: {e}")



def generate_video(user):
    global camera_active, cap, emotion_counts, prev_song, persisted_songs
    music_tracker = MusicTracker(user['id']) if user else MusicTracker(None)
    supabase = get_supabase()

    user_id = user['id'] if user else None
    current_song_id = None

    while True:
        if not camera_active or cap is None:
            blank = np.full((480,640,3), 200, np.uint8)
            cv2.putText(blank, "Camera Off", (220,240), cv2.FONT_HERSHEY_SIMPLEX, 1, (100,100,100), 2)
            ret, jpeg = cv2.imencode('.jpg', blank)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')
            continue

        ret, frame = cap.read()
        if not ret or frame is None:
            if camera_active:
                release_camera()
                if not init_camera():
                    camera_active = False
            continue

        # emotion detection
        res = detector.top_emotion(frame)
        if res is None or res[1] is None:
            detected_emotion, confidence = None, 0.0
            emotion_text = "Emotion: N/A"
        else:
            detected_emotion, confidence = res
            emotion_text = f"{detected_emotion} ({confidence:.2f})"
        frame = draw_text_with_border(frame, f"Emotion: {emotion_text}", (10,30))

        # get current song
        song_data = music_tracker.get_current_song(user_id) if user_id else {"name":"N/A","artist":"N/A","id":None}
        # Defensive: ensure song_data is a dict and fields exist
        if not isinstance(song_data, dict):
            song_data = {"name":"N/A","artist":"N/A","id":None}
        song_name = song_data.get('name') or "N/A"
        artist_name = song_data.get('artist') or "N/A"
        song_id = song_data.get('id', None)

        frame = draw_text_with_border(frame, f"Song: {song_name}", (10,70))
        frame = draw_text_with_border(frame, f"Artist: {artist_name}", (10,110))

        # Detect song change
        prev = prev_song.get(user_id)
        if song_id != prev:
            # Persist previous song using snapshot
            if prev and user_id in song_snapshot:
                snap = song_snapshot[user_id]
                persist_song_emotion(user_id, snap["id"], snap["name"], snap["artist"])
                old_key = f"{user_id}_{snap['id']}"
                if old_key in emotion_counts:
                    del emotion_counts[old_key]

            # Store new song snapshot
            if song_id:
                song_snapshot[user_id] = {"id": song_id, "name": song_name, "artist": artist_name}

        prev_song[user_id] = song_id


        # Count emotions using snapshot
        if song_id and detected_emotion:
            key = f"{user_id}_{song_id}"
            if key not in emotion_counts:
                emotion_counts[key] = Counter()
            emotion_counts[key][detected_emotion] += 1


        # yield frame
        ret, jpeg = cv2.imencode('.jpg', frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.getenv("PORT", 8888)))
