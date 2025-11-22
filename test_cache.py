import cache
import os
import time
from datetime import datetime, timedelta

def test_cache():
    print("Initializing DB...")
    cache.init_db()
    
    user_id = "test_user"
    data_key = "top_tracks"
    payload = [{"id": "t1", "name": "Track 1"}]
    
    print("Testing User Data Save/Load...")
    cache.save_user_spotify_data(user_id, data_key, payload)
    loaded = cache.load_user_spotify_data(user_id, data_key)
    
    assert loaded is not None
    assert loaded["payload"] == payload
    assert loaded["count"] == 1
    assert not cache.is_stale(loaded["last_fetched"])
    print("User Data: OK")
    
    print("Testing Artist Data Save/Load...")
    artist_id = "a1"
    artist_payload = [{"id": "t2", "name": "Track 2"}]
    cache.save_artist_top_tracks(artist_id, artist_payload)
    loaded_artist = cache.load_artist_top_tracks(artist_id)
    
    assert loaded_artist is not None
    assert loaded_artist["payload"] == artist_payload
    print("Artist Data: OK")
    
    print("Testing Track Features Save/Load...")
    features = [
        {"href": "https://api.reccobeats.com/v1/track/t1", "tempo": 120.5},
        {"href": "https://api.reccobeats.com/v1/track/t2", "tempo": None} # No tempo
    ]
    cache.save_track_features(features)
    
    loaded_features = cache.load_track_features(["t1", "t2", "t3"])
    assert "t1" in loaded_features
    assert loaded_features["t1"]["tempo"] == 120.5
    assert "t2" in loaded_features
    assert loaded_features["t2"]["tempo"] is None
    assert "t3" not in loaded_features
    print("Track Features: OK")
    
    print("Testing Recommendations Save/Load...")
    seed_id = "t1"
    recs = [{"href": "https://api.reccobeats.com/v1/track/t3"}]
    cache.save_reccobeats_recommendations(seed_id, recs)
    loaded_recs = cache.load_reccobeats_recommendations(seed_id)
    
    assert loaded_recs is not None
    assert loaded_recs["recs_json"] == recs
    print("Recommendations: OK")

    print("Testing Combined Tracks Save/Load...")
    combined = ["t1", "t2", "t3"]
    cache.save_user_combined_tracks(user_id, combined)
    loaded_combined = cache.load_user_combined_tracks(user_id)
    assert loaded_combined == combined
    print("Combined Tracks: OK")
    
    print("All cache tests passed!")

if __name__ == "__main__":
    if os.path.exists("cache.db"):
        try:
            os.remove("cache.db")
        except:
            pass
    test_cache()
