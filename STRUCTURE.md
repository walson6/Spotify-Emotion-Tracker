# Focus Tracker Web Application Structure

This document explains the Focus Tracker Web application.

### 📁 File Organization
```
├── app.py          # Main Flask app (78 lines) - routes and app configuration
├── auth.py         # Authentication (111 lines) - login, logout, user management
├── camera.py       # Camera & Video (200+ lines) - video capture, emotion detection, streaming
├── music.py        # Music (35 lines) - Spotify integration
├── models.py       # Data models (unchanged)
├── music_tracker.py # Music tracking (unchanged)
└── supabase_client.py # Database client (unchanged)
```

#### `app.py` - Main Application
- **Purpose**: Flask app configuration and route definitions
- **Responsibilities**: 
  - Initialize Flask app
  - Define all routes
  - Coordinate between managers

#### `auth.py` - Authentication
- **Purpose**: Handle all user authentication and session management
- **Responsibilities**:
  - User login/logout
  - Spotify OAuth flow
  - Session management
  - User data retrieval
- **Key Class**: `AuthManager`

#### `camera.py` - Camera & Video Processing
- **Purpose**: Handle camera operations, emotion detection, and video streaming
- **Responsibilities**:
  - Camera initialization and management
  - Video frame capture and processing
  - Emotion detection and tracking
  - Video stream generation
  - Song-emotion persistence
- **Key Class**: `CameraManager`

#### `music.py` - Music Integration
- **Purpose**: Handle Spotify music operations
- **Responsibilities**:
  - Current song retrieval
  - Music API responses
- **Key Class**: `MusicManager`

## Usage Example
```python
# app.py - Simple and clean
from auth import AuthManager
from camera import CameraManager
from music import MusicManager

# Initialize managers
auth_manager = AuthManager()
camera_manager = CameraManager()
music_manager = MusicManager()

# Routes are simple and delegate to managers
@app.route('/login')
def login():
    return auth_manager.login()
```