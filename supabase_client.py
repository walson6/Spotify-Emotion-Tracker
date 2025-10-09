# supabase_client.py
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

# Lazy import/create client to avoid import-time errors
_client = None

def get_supabase():
    global _client
    if _client:
        return _client
    try:
        from supabase.client import create_client, Client
    except Exception as e:
        raise RuntimeError("supabase package required. Install with 'pip install supabase'") from e
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment")
    _client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _client
