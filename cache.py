"""
SQLite caching layer for Spotify and ReccoBeats data.
"""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

DB_FILENAME = "cache.db"
CACHE_TTL_DAYS = 30


def get_db_path() -> str:
    """Return path to cache.db file."""
    return str(Path(__file__).parent / DB_FILENAME)


def get_db_conn() -> sqlite3.Connection:
    """Return sqlite3 connection with row factory and foreign keys enabled."""
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Initialize the database schema."""
    conn = get_db_conn()
    with conn:
        # Users
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                spotify_user_id TEXT PRIMARY KEY,
                display_name TEXT,
                email TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # User Spotify Data (top_tracks, saved_tracks, top_artists)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_spotify_data (
                spotify_user_id TEXT NOT NULL,
                data_key TEXT NOT NULL,
                payload JSON NOT NULL,
                count INTEGER,
                last_fetched TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (spotify_user_id, data_key)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_user_data_fetched ON user_spotify_data(last_fetched)")

        # Artist Top Tracks
        conn.execute("""
            CREATE TABLE IF NOT EXISTS artist_top_tracks (
                artist_id TEXT PRIMARY KEY,
                payload JSON NOT NULL,
                count INTEGER,
                last_fetched TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_artist_tracks_fetched ON artist_top_tracks(last_fetched)")

        # Track Features (ReccoBeats)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS track_features (
                spotify_id TEXT PRIMARY KEY,
                tempo REAL,
                features_json JSON,
                last_fetched TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fetch_status TEXT NOT NULL DEFAULT 'ok'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_track_features_fetched ON track_features(last_fetched)")

        # ReccoBeats Recommendations
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reccobeats_recommendations (
                spotify_seed_id TEXT PRIMARY KEY,
                recs_json JSON NOT NULL,
                count INTEGER,
                last_fetched TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # User Combined Tracks
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_combined_tracks (
                spotify_user_id TEXT PRIMARY KEY,
                track_ids JSON NOT NULL,
                count INTEGER,
                last_fetched TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.close()


# --- Helpers ---

def is_stale(last_fetched: Union[str, datetime], days: int = CACHE_TTL_DAYS) -> bool:
    """Return True if last_fetched is older than days."""
    if isinstance(last_fetched, str):
        try:
            last_fetched = datetime.fromisoformat(last_fetched)
        except ValueError:
            return True  # Invalid format, treat as stale
    
    # Ensure last_fetched is offset-naive or convert both to UTC if needed.
    # SQLite current_timestamp is usually UTC string.
    # We'll stick to naive UTC for simplicity.
    if last_fetched.tzinfo:
        last_fetched = last_fetched.replace(tzinfo=None)
        
    return datetime.utcnow() - last_fetched > timedelta(days=days)


def extract_spotify_id_from_href(href: Optional[str]) -> Optional[str]:
    """Extract the Spotify track ID from a ReccoBeats href."""
    if not href:
        return None
    if "track/" in href:
        segment = href.split("track/", maxsplit=1)[-1]
    else:
        segment = href
    segment = segment.split("?", maxsplit=1)[0]
    return segment or None


# --- User Spotify Data ---

def load_user_spotify_data(spotify_user_id: str, data_key: str) -> Optional[dict]:
    """Return payload dict if present."""
    conn = get_db_conn()
    row = conn.execute(
        "SELECT payload, count, last_fetched FROM user_spotify_data WHERE spotify_user_id = ? AND data_key = ?",
        (spotify_user_id, data_key)
    ).fetchone()
    conn.close()
    
    if row:
        return {
            "payload": json.loads(row["payload"]),
            "count": row["count"],
            "last_fetched": row["last_fetched"]
        }
    return None


def save_user_spotify_data(spotify_user_id: str, data_key: str, payload: Any) -> None:
    """Upsert user spotify data."""
    count = len(payload) if isinstance(payload, list) else 0
    conn = get_db_conn()
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO user_spotify_data (spotify_user_id, data_key, payload, count, last_fetched)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (spotify_user_id, data_key, json.dumps(payload), count)
        )
    conn.close()


# --- Artist Top Tracks ---

def load_artist_top_tracks(artist_id: str) -> Optional[dict]:
    """Return artist top tracks payload if present."""
    conn = get_db_conn()
    row = conn.execute(
        "SELECT payload, count, last_fetched FROM artist_top_tracks WHERE artist_id = ?",
        (artist_id,)
    ).fetchone()
    conn.close()

    if row:
        return {
            "payload": json.loads(row["payload"]),
            "count": row["count"],
            "last_fetched": row["last_fetched"]
        }
    return None


def save_artist_top_tracks(artist_id: str, payload: Any) -> None:
    """Upsert artist top tracks."""
    count = len(payload) if isinstance(payload, list) else 0
    conn = get_db_conn()
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO artist_top_tracks (artist_id, payload, count, last_fetched)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (artist_id, json.dumps(payload), count)
        )
    conn.close()


# --- Track Features (Tempo) ---

def load_track_features(spotify_ids: Sequence[str]) -> Dict[str, dict]:
    """
    Return mapping spotify_id -> {'tempo': float|None, 'features': dict|None, 'last_fetched': datetime, 'fetch_status': str}
    """
    if not spotify_ids:
        return {}
        
    placeholders = ",".join("?" * len(spotify_ids))
    conn = get_db_conn()
    rows = conn.execute(
        f"SELECT spotify_id, tempo, features_json, last_fetched, fetch_status FROM track_features WHERE spotify_id IN ({placeholders})",
        list(spotify_ids)
    ).fetchall()
    conn.close()

    result = {}
    for row in rows:
        result[row["spotify_id"]] = {
            "tempo": row["tempo"],
            "features": json.loads(row["features_json"]) if row["features_json"] else None,
            "last_fetched": row["last_fetched"],
            "fetch_status": row["fetch_status"]
        }
    return result


def save_track_features(feature_objs: Sequence[dict]) -> None:
    """
    Upsert track features.
    feature_objs: List of raw ReccoBeats response objects (must contain 'href').
    """
    conn = get_db_conn()
    with conn:
        for obj in feature_objs:
            href = obj.get("href")
            spotify_id = extract_spotify_id_from_href(href)
            if not spotify_id:
                continue
            
            tempo = obj.get("tempo")
            try:
                tempo_val = float(tempo) if tempo is not None else None
            except (ValueError, TypeError):
                tempo_val = None
            
            conn.execute(
                """
                INSERT OR REPLACE INTO track_features (spotify_id, tempo, features_json, last_fetched, fetch_status)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'ok')
                """,
                (spotify_id, tempo_val, json.dumps(obj))
            )
    conn.close()


def mark_tracks_no_data(spotify_ids: Sequence[str]) -> None:
    """Mark tracks as 'no_data' to prevent repeated fetching."""
    conn = get_db_conn()
    with conn:
        for spotify_id in spotify_ids:
            conn.execute(
                """
                INSERT OR REPLACE INTO track_features (spotify_id, tempo, features_json, last_fetched, fetch_status)
                VALUES (?, NULL, NULL, CURRENT_TIMESTAMP, 'no_data')
                """,
                (spotify_id,)
            )
    conn.close()


# --- Recommendations ---

def load_reccobeats_recommendations(seed_track_id: str) -> Optional[dict]:
    """Return recommendations payload if present."""
    conn = get_db_conn()
    row = conn.execute(
        "SELECT recs_json, count, last_fetched FROM reccobeats_recommendations WHERE spotify_seed_id = ?",
        (seed_track_id,)
    ).fetchone()
    conn.close()

    if row:
        return {
            "recs_json": json.loads(row["recs_json"]),
            "count": row["count"],
            "last_fetched": row["last_fetched"]
        }
    return None


def save_reccobeats_recommendations(seed_track_id: str, recs_list: Sequence[dict]) -> None:
    """Upsert recommendations."""
    count = len(recs_list)
    conn = get_db_conn()
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO reccobeats_recommendations (spotify_seed_id, recs_json, count, last_fetched)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (seed_track_id, json.dumps(recs_list), count)
        )
    conn.close()


# --- Combined Tracks ---

def load_user_combined_tracks(spotify_user_id: str) -> Optional[List[str]]:
    """Return list of combined track IDs if present."""
    conn = get_db_conn()
    row = conn.execute(
        "SELECT track_ids, last_fetched FROM user_combined_tracks WHERE spotify_user_id = ?",
        (spotify_user_id,)
    ).fetchone()
    conn.close()

    if row:
        return json.loads(row["track_ids"])
    return None


def save_user_combined_tracks(spotify_user_id: str, track_ids: Sequence[str]) -> None:
    """Upsert combined track IDs."""
    count = len(track_ids)
    conn = get_db_conn()
    with conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO user_combined_tracks (spotify_user_id, track_ids, count, last_fetched)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (spotify_user_id, json.dumps(track_ids), count)
        )
    conn.close()
