"""Running Playlist Generator Flask app."""

from __future__ import annotations

import csv
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    flash,
    json,
    redirect,
    render_template,
    request,
    session,
    stream_with_context,
    url_for,
)
import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError


load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

# Initialize Cache
import cache
cache.init_db()

SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID")
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:5000/callback")
SPOTIFY_SCOPE = " ".join(
    [
        "user-read-email",
        "user-top-read",
        "user-library-read",
        "playlist-modify-public",
        "playlist-modify-private",
    ]
)

CADENCE_OPTIONS = [140, 150, 160, 170, 180, 190]
TEMPO_TOLERANCE = 5
RECCOBEATS_URL = "https://api.reccobeats.com/v1/audio-features"


class PlaylistGenerationError(Exception):
    """Raised when a playlist could not be created."""


def spotify_configured() -> bool:
    """Return True when Spotify credentials were supplied."""
    return bool(SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET)


from spotipy.cache_handler import CacheHandler


class NoCacheHandler(CacheHandler):
    """A cache handler that does nothing, preventing token persistence to disk."""

    def get_cached_token(self):
        return None

    def save_token_to_cache(self, token_info):
        pass


def get_spotify_oauth() -> SpotifyOAuth:
    """Build a SpotifyOAuth helper with the demo's settings."""
    if not spotify_configured():
        raise RuntimeError(
            "Spotify credentials are missing. Check SPOTIPY_CLIENT_ID/SECRET."
        )

    return SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=SPOTIFY_SCOPE,
        cache_handler=NoCacheHandler(),
        show_dialog=True,  # Force dialog to allow account switching
    )


@app.after_request
def add_header(response):
    """Add headers to both force latest IE rendering engine or Chrome Frame,
    and also to cache the rendered page for 10 minutes."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def refresh_token_if_expired() -> Optional[dict]:
    """Return a valid token_info, refreshing if necessary."""
    token_info = session.get("token_info")
    if not token_info:
        return None

    try:
        oauth = get_spotify_oauth()
        if oauth.is_token_expired(token_info):
            token_info = oauth.refresh_access_token(token_info["refresh_token"])
            session["token_info"] = token_info
        return token_info
    except (SpotifyOauthError, RuntimeError) as exc:
        flash(f"Spotify session expired: {exc}", "error")
        session.pop("token_info", None)
        session.pop("user", None)
        return None


def get_spotify_client() -> Optional[spotipy.Spotify]:
    """Instantiate a Spotipy client from the current user session."""
    token_info = refresh_token_if_expired()
    if not token_info:
        return None
    return spotipy.Spotify(auth=token_info["access_token"])


def fetch_user_top_tracks(sp: spotipy.Spotify, user_id: str, limit: int = 50) -> List[dict]:
    """Return the user's top tracks (may be empty)."""
    cached = cache.load_user_spotify_data(user_id, "top_tracks")
    if cached and not cache.is_stale(cached["last_fetched"]):
        return cached["payload"]

    try:
        response = sp.current_user_top_tracks(limit=limit, time_range="medium_term")
        items = response.get("items", [])
        cache.save_user_spotify_data(user_id, "top_tracks", items)
        return items
    except spotipy.SpotifyException:
        return []


def fetch_user_saved_tracks(sp: spotipy.Spotify, user_id: str, limit: int = 50) -> List[dict]:
    """Return the user's saved tracks as plain track dictionaries."""
    cached = cache.load_user_spotify_data(user_id, "saved_tracks")
    if cached and not cache.is_stale(cached["last_fetched"]):
        return cached["payload"]

    tracks: List[dict] = []
    offset = 0
    try:
        while True:
            response = sp.current_user_saved_tracks(limit=limit, offset=offset)
            items = response.get("items", [])
            if not items:
                break
            for item in items:
                track = item.get("track")
                if track and track.get("id"):
                    tracks.append(track)
            offset += len(items)
            if len(items) < limit:
                break
        cache.save_user_spotify_data(user_id, "saved_tracks", tracks)
    except spotipy.SpotifyException as exc:
        print("saved_tracks error:", exc)
    return tracks



def fetch_user_top_artists(sp: spotipy.Spotify, user_id: str, limit: int = 50) -> List[dict]:
    """Return the user's top artists."""
    cached = cache.load_user_spotify_data(user_id, "top_artists")
    if cached and not cache.is_stale(cached["last_fetched"]):
        return cached["payload"]

    try:
        response = sp.current_user_top_artists(limit=limit, time_range="medium_term")
        items = response.get("items", [])
        cache.save_user_spotify_data(user_id, "top_artists", items)
        return items
    except spotipy.SpotifyException:
        return []


def fetch_artist_top_tracks(sp: spotipy.Spotify, artist_id: str) -> List[dict]:
    """Return the top tracks for a given artist."""
    cached = cache.load_artist_top_tracks(artist_id)
    if cached and not cache.is_stale(cached["last_fetched"]):
        return cached["payload"]

    try:
        response = sp.artist_top_tracks(artist_id)
        tracks = response.get("tracks", [])
        cache.save_artist_top_tracks(artist_id, tracks)
        return tracks
    except spotipy.SpotifyException:
        return []


def collect_user_tracks(sp: spotipy.Spotify, user_id: str) -> Tuple[List[dict], List[dict]]:
    """Return the user's top tracks and saved tracks (deduped within each list)."""
    top_tracks = fetch_user_top_tracks(sp, user_id, limit=50)
    saved_tracks = fetch_user_saved_tracks(sp, user_id, limit=50)

    def dedupe(tracks: List[dict]) -> List[dict]:
        seen: Dict[str, dict] = {}
        for track in tracks:
            track_id = track.get("id")
            if track_id and track_id not in seen:
                seen[track_id] = track
        return list(seen.values())

    return dedupe(top_tracks), dedupe(saved_tracks)





def fetch_similar_tracks_for_top_tracks(
    top_tracks: List[dict],
    size: int = 20,
    delay_seconds: float = 0.1,
) -> List[str]:
    """Use ReccoBeats to find similar tracks for each top track."""
    similar_ids: set[str] = set()
    headers = {"Accept": "application/json"}
    
    for track in top_tracks:
        track_id = track.get("id")
        if not track_id:
            continue
            
        # Check cache
        cached = cache.load_reccobeats_recommendations(track_id)
        if cached and not cache.is_stale(cached["last_fetched"]):
            for rec in cached["recs_json"]:
                href = rec.get("href")
                sid = cache.extract_spotify_id_from_href(href)
                if sid:
                    similar_ids.add(sid)
            continue

        # Fetch from API
        params = {"size": size, "seeds": track_id}
        try:
            response = requests.get(
                "https://api.reccobeats.com/v1/track/recommendation",
                headers=headers,
                params=params,
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload.get("content") if isinstance(payload, dict) else None
            
            if isinstance(content, list):
                # Save to cache
                cache.save_reccobeats_recommendations(track_id, content)
                
                for entry in content:
                    href = entry.get("href")
                    similar_id = cache.extract_spotify_id_from_href(href)
                    if similar_id:
                        similar_ids.add(similar_id)
        except requests.RequestException as exc:
            print(f"recommendation error for {track_id}: {exc}")
            continue
        time.sleep(delay_seconds)
        
    print(f"Similar track IDs discovered (deduped): {len(similar_ids)}")
    return list(similar_ids)


def fetch_missing_tempos_with_reccobeats(
    track_ids: List[str],
) -> Dict[str, dict]:
    """Fetch tempo data for IDs not yet cached or stale."""
    if not track_ids:
        return {}

    # Load existing from cache
    cached_data = cache.load_track_features(track_ids)
    
    # Identify missing or stale IDs
    missing_ids = []
    for tid in track_ids:
        entry = cached_data.get(tid)
        if not entry:
            missing_ids.append(tid)
        elif entry["fetch_status"] == "ok" and cache.is_stale(entry["last_fetched"]):
            missing_ids.append(tid)
        # If fetch_status is 'no_data' and not stale, we skip it (don't fetch again)
        # If fetch_status is 'no_data' and stale, we could retry. Let's retry.
        elif entry["fetch_status"] == "no_data" and cache.is_stale(entry["last_fetched"]):
            missing_ids.append(tid)

    if not missing_ids:
        return cached_data

    headers = {"Accept": "application/json"}
    print(f"Fetching {len(missing_ids)} missing IDs")
    
    for i in range(0, len(missing_ids), 40):
        chunk = missing_ids[i : i + 40]
        try:
            response = requests.get(
                RECCOBEATS_URL,
                headers=headers,
                params={"ids": ",".join(chunk)},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload.get("content") if isinstance(payload, dict) else None
            
            if isinstance(content, list):
                cache.save_track_features(content)
                
                # Identify which IDs in this chunk got NO data
                # Get IDs returned in content
                returned_ids = set()
                for obj in content:
                    sid = cache.extract_spotify_id_from_href(obj.get("href"))
                    if sid:
                        returned_ids.add(sid)
                
                # Find which requested IDs were not returned
                no_data_ids = [cid for cid in chunk if cid not in returned_ids]
                if no_data_ids:
                    cache.mark_tracks_no_data(no_data_ids)

        except requests.RequestException as exc:
            print(f"ReccoBeats error: {exc}")
            # Optionally mark chunk as error or just skip
            continue

    # Reload cache to get the newly saved data
    return cache.load_track_features(track_ids)


def filter_tracks_by_tempo(
    track_ids: List[str],
    tempo_data: Dict[str, dict],
    cadence_bpm: int,
) -> List[dict]:
    """Return tracks whose tempo falls within cadence and cadence + 9."""
    min_bpm = cadence_bpm
    max_bpm = cadence_bpm + 9
    filtered_ids: List[str] = []

    for track_id in track_ids:
        metrics = tempo_data.get(track_id)
        if not metrics or metrics["fetch_status"] != "ok":
            continue
            
        tempo = metrics.get("tempo")
        if tempo is None:
            continue
            
        if min_bpm <= tempo <= max_bpm:
            filtered_ids.append(track_id)
    print(f"Tracks within tempo range: {len(filtered_ids)}")
    return filtered_ids


def build_playlist_with_tempo_data(
    sp: spotipy.Spotify,
    user_id: str,
    cadence_bpm: int,
    track_ids: List[str],
) -> dict:
    """Create a cadence playlist using the provided track list."""
    if not track_ids:
        raise PlaylistGenerationError(
            "No tracks matched that cadence. Adjust your stride or add more music."
        )

    # Construct URIs directly from IDs (works for top, saved, AND similar tracks)
    track_uris = [f"spotify:track:{tid}" for tid in track_ids]

    if not track_uris:
        raise PlaylistGenerationError(
            "None of the matched tracks are playable right now. Please try again."
        )

    playlist = sp.user_playlist_create(
        user=user_id,
        name=f"Run Cadence {cadence_bpm} BPM",
        public=False,
        collaborative=False,
        description="Generated by Running Playlist Generator",
    )

    for i in range(0, len(track_uris), 100):
        sp.playlist_add_items(playlist_id=playlist["id"], items=track_uris[i : i + 100])

    external_url = playlist["external_urls"]["spotify"]
    embed_url = f"https://open.spotify.com/embed/playlist/{playlist['id']}"
    return {
        "id": playlist["id"],
        "name": playlist["name"],
        "url": external_url,
        "embed_url": embed_url,
    }


@app.route("/")
def index():
    user = session.get("user")
    playlist = session.get("last_playlist")
    configured = spotify_configured()
    return render_template(
        "index.html",
        user=user,
        playlist=playlist,
        configured=configured,
        cadence_options=CADENCE_OPTIONS,
        selected_preferences=session.get("last_preferences"),
    )


@app.route("/login")
def login():
    if not spotify_configured():
        flash(
            "Spotify credentials missing. Update your .env file with SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET.",
            "error",
        )
        return redirect(url_for("index"))

    token_info = refresh_token_if_expired()
    if token_info:
        return redirect(url_for("index"))

    oauth = get_spotify_oauth()
    auth_url = oauth.get_authorize_url()
    return redirect(auth_url)


@app.route("/callback")
def callback():
    error = request.args.get("error")
    if error:
        flash(f"Spotify authorization failed: {error}", "error")
        return redirect(url_for("index"))

    code = request.args.get("code")
    if not code:
        flash("Missing authorization code. Please try again.", "error")
        return redirect(url_for("index"))

    try:
        oauth = get_spotify_oauth()
        token_info = oauth.get_access_token(code, as_dict=True)
    except SpotifyOauthError as exc:
        flash(f"Could not complete Spotify login: {exc}", "error")
        return redirect(url_for("index"))

    session["token_info"] = token_info

    sp = spotipy.Spotify(auth=token_info["access_token"])
    try:
        profile = sp.current_user()
    except spotipy.SpotifyException as exc:
        flash(f"Could not load your Spotify profile: {exc}", "error")
        session.pop("token_info", None)
        return redirect(url_for("index"))

    session["user"] = {
        "id": profile.get("id"),
        "display_name": profile.get("display_name") or profile.get("id", "Spotify user"),
        "email": profile.get("email") or "No email returned",
    }

    flash("Spotify account connected. Ready to run!", "success")
    return redirect(url_for("index"))


def generate_playlist_logic(user, cadence, sp):
    """Generator that yields SSE events for playlist creation."""
    try:
        user_id = user["id"]
        
        # Step 1: Fetch user's top tracks
        yield f"data: {json.dumps({'type': 'status', 'message': 'Digging through your top tracks… let’s see what heat you’ve been vibing to.'})}\n\n"
        top_tracks = fetch_user_top_tracks(sp, user_id, limit=50)
        
        # Step 2: Fetch user's saved tracks (ALL)
        yield f"data: {json.dumps({'type': 'status', 'message': f'Nice picks — found {len(top_tracks)} favorites. Diving into your saved stash next…'})}\n\n"
        saved_tracks = fetch_user_saved_tracks(sp, user_id, limit=50)
        
        # Step 3: Fetch user's top artists
        yield f"data: {json.dumps({'type': 'status', 'message': 'Calling in your top artists, hm we got a nice bunch here....'})}\n\n"
        top_artists = fetch_user_top_artists(sp, user_id, limit=50)

        # Step 4: Fetch each top artist's top tracks
        yield f"data: {json.dumps({'type': 'status', 'message': 'Asking your top artists for their greatest hits. We music twins now....'})}\n\n"
        artist_tracks = []
        for artist in top_artists:
            artist_id = artist.get("id")
            if artist_id:
                tracks = fetch_artist_top_tracks(sp, artist_id)
                artist_tracks.extend(tracks)
        
        # Step 5: Conditional Recommendations
        similar_ids = []
        if len(saved_tracks) < 500:
            yield f"data: {json.dumps({'type': 'status', 'message': 'Sending out the search party for music similar to your favorites, this might take a minute....'})}\n\n"
            similar_ids = fetch_similar_tracks_for_top_tracks(top_tracks, size=3)

        # Step 6: Consolidate
        top_ids = [track.get("id") for track in top_tracks if track.get("id")]
        saved_ids = [track.get("id") for track in saved_tracks if track.get("id")]
        artist_track_ids = [track.get("id") for track in artist_tracks if track.get("id")]
        
        all_track_ids = list(set(top_ids + saved_ids + artist_track_ids + similar_ids))
        
        if not all_track_ids:
             yield f"data: {json.dumps({'type': 'error', 'message': 'We could not find enough tracks in your library.'})}\n\n"
             return
             
        # Save combined tracks to cache
        cache.save_user_combined_tracks(user_id, all_track_ids)

        # Step 7 & 8: Tempo Cache & Filter
        yield f"data: {json.dumps({'type': 'status', 'message': f'Collected {len(all_track_ids):,} tracks. Time to check their BPMs — this might take a minute, scroll some reels...'})}\n\n"

        # Fetch/Load tempo data (returns dict of spotify_id -> feature_obj)
        tempo_data = fetch_missing_tempos_with_reccobeats(all_track_ids)

        # Step 9: Filter
        filtered_ids = filter_tracks_by_tempo(
            all_track_ids, tempo_data, cadence
        )

        # Step 10: Create Playlist
        yield f"data: {json.dumps({'type': 'status', 'message': f'BPMs locked in. Found {len(filtered_ids)} songs matching {cadence}-{cadence+9} BPM. Assembling your run-ready playlist…'})}\n\n"

        playlist = build_playlist_with_tempo_data(
            sp=sp,
            user_id=user_id,
            cadence_bpm=cadence,
            track_ids=filtered_ids,
        )
        
        # Step 11: Done
        yield f"data: {json.dumps({'type': 'status', 'message': 'Your playlist is cooked and ready! Lace up — take them for a runnn 🏃‍♂️🔥'})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'message': 'Done!', 'playlist_url': playlist['url'], 'embed_url': playlist['embed_url']})}\n\n"

    except Exception as e:
        print(f"Error in generation: {e}")
        yield f"data: {json.dumps({'type': 'error', 'message': 'Oops — something hiccuped. The playlist run had to stop. Give it another shot!'})}\n\n"


@app.route("/generate_stream")
def generate_stream():
    if not session.get("user"):
        return Response(
            f"data: {json.dumps({'type': 'error', 'message': 'Please connect with Spotify first.'})}\n\n",
            mimetype="text/event-stream",
        )

    sp = get_spotify_client()
    if not sp:
        return Response(
            f"data: {json.dumps({'type': 'error', 'message': 'Please reconnect to Spotify.'})}\n\n",
            mimetype="text/event-stream",
        )

    try:
        cadence = int(request.args.get("cadence", CADENCE_OPTIONS[0]))
    except (TypeError, ValueError):
        return Response(
             f"data: {json.dumps({'type': 'error', 'message': 'Invalid cadence.'})}\n\n",
            mimetype="text/event-stream",
        )

    user = session["user"]
    
    # Save preference just like before
    session["last_preferences"] = {"cadence": cadence}

    return Response(
        stream_with_context(generate_playlist_logic(user, cadence, sp)),
        mimetype="text/event-stream",
    )


# Keep the old route for fallback or direct POST if needed, but it's largely replaced.
@app.route("/generate", methods=["POST"])
def generate_playlist():
    # Redirect to index since we are moving to JS-driven flow
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Signed out.", "info")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)

