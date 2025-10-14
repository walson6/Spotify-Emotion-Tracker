# camera.py
"""
Camera module - handles video capture, emotion detection, and video streaming.
"""
import cv2
import numpy as np
from typing import Optional, Tuple, Generator, Dict, Any
from PIL import Image, ImageDraw, ImageFont
from fer import FER
from collections import Counter
from supabase_client import get_supabase
from music_tracker import MusicTracker


class CameraManager:
    """Handles all camera and video processing operations."""
    
    def __init__(self):
        self.detector = FER()
        self.cap: Optional[cv2.VideoCapture] = None
        self.camera_active = False
        self.camera_initializing = False
        
        # Emotion tracking
        self.emotion_counts: Dict[str, Counter] = {}
        self.prev_song: Dict[int, Optional[str]] = {}
        self.persisted_songs: set = set()
        self.song_snapshot: Dict[int, Dict] = {}
    
    def init_camera(self) -> bool:
        """Initialize camera with fallback backends."""
        if self.camera_initializing or self.cap:
            return False
        
        self.camera_initializing = True
        backends = [
            (cv2.CAP_DSHOW, "DirectShow"), 
            (cv2.CAP_MSMF, "Media Foundation"), 
            (cv2.CAP_ANY, "Any")
        ]
        
        for backend, _name in backends:
            for idx in range(3):
                try:
                    self.cap = cv2.VideoCapture(idx, backend)
                    if self.cap.isOpened():
                        ret, frame = self.cap.read()
                        if ret and frame is not None:
                            self.camera_initializing = False
                            return True
                        self.cap.release()
                        self.cap = None
                except Exception:
                    if self.cap:
                        self.cap.release()
                        self.cap = None
        
        self.camera_initializing = False
        self.cap = None
        return False
    
    def release_camera(self):
        """Release camera resources."""
        if self.cap:
            self.cap.release()
            self.cap = None
    
    def toggle_camera(self) -> Tuple[bool, str]:
        """Toggle camera on/off and persist current song emotion when turning off."""
        if self.camera_initializing:
            return False, "Camera initializing"
        
        self.camera_active = not self.camera_active

        if self.camera_active and not self.init_camera():
            self.camera_active = False
            return False, "Failed to start camera"
        
        if not self.camera_active:
            # Persist current song's emotion when camera stops
            self.persist_current_song_emotion()
            self.release_camera()
        
        return True, "Success"

    def create_blank_frame(self, text: str = "Camera Off") -> np.ndarray:
        """Create a blank frame with text."""
        blank = np.full((480, 640, 3), 200, np.uint8)
        cv2.putText(blank, text, (220, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (100, 100, 100), 2)
        return blank
    
    def draw_text_with_border(self, img: np.ndarray, text: str, position: Tuple[int, int], font_size: int = 26) -> np.ndarray:
        """Draw text with border on image."""
        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil)
        
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        
        # Draw border
        for ox, oy in [(1, 1), (-1, -1), (1, -1), (-1, 1)]:
            draw.text((position[0] + ox, position[1] + oy), text, font=font, fill=(255, 255, 255))
        
        # Draw main text
        draw.text(position, text, font=font, fill=(0, 0, 0))
        
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    
    def detect_emotion(self, frame, visualize=False):
        results = self.detector.detect_emotions(frame)
        if not results:
            return None, 0.0, frame

        # Use the first detected face
        face = results[0]
        (x, y, w, h) = face["box"]
        emotions = face["emotions"]
        top_emotion = max(emotions, key=emotions.get)
        confidence = emotions[top_emotion]

        if visualize:
            # Draw rectangle around face
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
            # Label emotion
            cv2.putText(frame, f"{top_emotion} ({confidence:.2f})",
                        (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (0, 255, 0), 2)

        return top_emotion, confidence, frame
    
    def track_emotion(self, user_id: int, song_id: str, emotion: str):
        """Track emotion for a specific user and song."""
        if not song_id or not emotion:
            return
        
        key = f"{user_id}_{song_id}"
        if key not in self.emotion_counts:
            self.emotion_counts[key] = Counter()
        self.emotion_counts[key][emotion] += 1
    
    def persist_song_emotion(self, user_id: int, song_id: str, song_name: str, artist_name: str):
        """Persist the majority emotion for a song."""
        key = f"{user_id}_{song_id}"
        if key not in self.emotion_counts:
            return
        
        counts = self.emotion_counts[key]
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
            self.persisted_songs.add(key)
        except Exception as e:
            print(f"[CameraManager] Error persisting song emotion for {key}: {e}")

    def persist_current_song_emotion(self):
        """Persist emotion data only for the current song when camera is toggled off."""
        for user_id, snap in self.song_snapshot.items():
            current_song_id = snap.get("id")
            song_name = snap.get("name")
            artist_name = snap.get("artist")

            if not current_song_id:
                continue

            key = f"{user_id}_{current_song_id}"
            if key in self.emotion_counts and self.emotion_counts[key]:
                self.persist_song_emotion(user_id, current_song_id, song_name, artist_name)

    def handle_song_change(self, user_id: int, current_song_id: str, song_name: str, artist_name: str):
        """Handle song change and persist previous song's emotion."""
        prev = self.prev_song.get(user_id)
        
        if current_song_id != prev:
            # Persist previous song using snapshot
            if prev and user_id in self.song_snapshot:
                snap = self.song_snapshot[user_id]
                self.persist_song_emotion(user_id, snap["id"], snap["name"], snap["artist"])
                old_key = f"{user_id}_{snap['id']}"
                if old_key in self.emotion_counts:
                    del self.emotion_counts[old_key]
            
            # Store new song snapshot
            if current_song_id:
                self.song_snapshot[user_id] = {
                    "id": current_song_id, 
                    "name": song_name, 
                    "artist": artist_name
                }
        
        self.prev_song[user_id] = current_song_id
    
    def generate_video(self, user: Optional[Dict[str, Any]]) -> Generator[bytes, None, None]:
        """Generate video stream with emotion detection and music tracking."""
        music_tracker = MusicTracker(user['id']) if user else MusicTracker(None)
        user_id = user['id'] if user else None
        
        while True:
            if not self.camera_active or self.cap is None:
                blank = self.create_blank_frame()
                ret, jpeg = cv2.imencode('.jpg', blank)
                yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')
                continue
            
            ret, frame = self.cap.read()
            if not ret or frame is None:
                if self.camera_active:
                    self.release_camera()
                    if not self.init_camera():
                        self.camera_active = False
                continue
            
            # Emotion detection
            detected_emotion, confidence, frame = self.detect_emotion(frame, visualize=True)
            if detected_emotion is None:
                emotion_text = "Emotion: N/A"
            else:
                emotion_text = f"{detected_emotion} ({confidence:.2f})"
            
            frame = self.draw_text_with_border(frame, f"Emotion: {emotion_text}", (10, 20))
            
            # Get current song
            song_data = music_tracker.get_current_song(user_id) if user_id else {"name": "N/A", "artist": "N/A", "id": None}
            if not isinstance(song_data, dict):
                song_data = {"name": "N/A", "artist": "N/A", "id": None}
            
            song_name = song_data.get('name') or "N/A"
            artist_name = song_data.get('artist') or "N/A"
            song_id = song_data.get('id', None)
            
            frame = self.draw_text_with_border(frame, f"Song: {song_name}", (10, 55))
            frame = self.draw_text_with_border(frame, f"Artist: {artist_name}", (10, 90))
            
            # Handle song change and emotion tracking
            self.handle_song_change(user_id, song_id, song_name, artist_name)
            
            # Track emotion for current song
            if song_id and detected_emotion:
                self.track_emotion(user_id, song_id, detected_emotion)
            
            # Yield frame
            ret, jpeg = cv2.imencode('.jpg', frame)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')
