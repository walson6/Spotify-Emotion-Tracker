# models.py
from datetime import datetime, timedelta, timezone
from typing import Optional
from dataclasses import dataclass, field
from supabase_client import get_supabase

@dataclass
class User:
    id: int
    spotify_id: str
    email: Optional[str]
    display_name: Optional[str]
    created_at: datetime

    @staticmethod
    def _parse_row(row: dict) -> dict:
        if isinstance(row.get('created_at'), str):
            row['created_at'] = datetime.fromisoformat(row['created_at'])
        return row

    @staticmethod
    def get_by_spotify_id(spotify_id: str) -> Optional['User']:
        supabase = get_supabase()
        res = supabase.table('users').select('*').eq('spotify_id', spotify_id).execute()
        if res.data:
            data = User._parse_row(res.data[0])
            return User(**data)
        return None

    @staticmethod
    def create(spotify_id: str, email: Optional[str] = None, display_name: Optional[str] = None) -> 'User':
        supabase = get_supabase()
        payload = {'spotify_id': spotify_id, 'email': email, 'display_name': display_name}
        res = supabase.table('users').insert(payload).execute()
        data = User._parse_row(res.data[0])
        return User(**data)


@dataclass
class SpotifyToken:
    id: int
    user_id: int
    access_token: str
    refresh_token: str
    expires_at: datetime = field(repr=False)

    def __post_init__(self):
        if isinstance(self.expires_at, str):
            try:
                self.expires_at = datetime.fromisoformat(self.expires_at)
            except Exception:
                # fallback: try to parse naive format
                self.expires_at = datetime.strptime(self.expires_at.split('+')[0], "%Y-%m-%dT%H:%M:%S.%f")

    def is_expired(self) -> bool:
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return now >= expires

    @staticmethod
    def get_by_user_id(user_id: int) -> Optional['SpotifyToken']:
        if not user_id:
            return None
        supabase = get_supabase()
        res = supabase.table('spotify_tokens').select('*').eq('user_id', user_id).execute()
        if res.data:
            return SpotifyToken(**res.data[0])
        return None

    @staticmethod
    def create_or_update(user_id: int, access_token: str, refresh_token: str, expires_in: int) -> 'SpotifyToken':
        supabase = get_supabase()
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        payload = {
            'user_id': user_id,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': expires_at.isoformat()
        }
        existing = supabase.table('spotify_tokens').select('id').eq('user_id', user_id).execute()
        if existing.data:
            res = supabase.table('spotify_tokens').update(payload).eq('user_id', user_id).execute()
        else:
            res = supabase.table('spotify_tokens').insert(payload).execute()
        return SpotifyToken(**res.data[0])
