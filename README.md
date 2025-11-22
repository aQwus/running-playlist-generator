# Running Playlist Generator

A Flask web application that generates Spotify running playlists matched to your cadence (steps per minute). The app uses your Spotify listening history and the ReccoBeats API to find tracks that match your running rhythm.

## Features

- **Spotify Integration**: OAuth authentication with automatic session management
- **Smart Track Selection**: Analyzes your top tracks, saved tracks, and discovers similar songs
- **Tempo Matching**: Finds tracks within your target cadence range (140–190 BPM)
- **Real-time Progress**: Live updates during playlist generation via Server-Sent Events
- **Intelligent Caching**: SQLite database stores tempo data and recommendations for 30 days
- **Modern UI**: Dark theme with responsive design inspired by athletic aesthetics
- **White-label Dropdown**: Accessible dropdown menus with high-contrast options

## How It Works

1. **Authentication**: Connects to your Spotify account with permissions for reading library and creating playlists
2. **Data Collection**: Gathers your top 50 tracks and recently saved tracks
3. **Expansion**: For each top track, fetches up to 100 similar recommendations from ReccoBeats
4. **Tempo Analysis**: Retrieves tempo data via ReccoBeats API and caches it locally
5. **Filtering**: Selects tracks within your target cadence ±4 BPM (10 BPM range total)
6. **Playlist Creation**: Creates a private Spotify playlist named `Run Cadence <XXX> BPM`

## Setup Instructions

### 1. Create a Spotify Developer App

1. Visit the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. In **Settings → Redirect URIs**, add exactly: `http://127.0.0.1:5000/callback`
   - ⚠️ Use `127.0.0.1` not `localhost` (Spotify treats them as different URIs)
4. Copy your **Client ID** and **Client Secret**

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```env
SPOTIPY_CLIENT_ID=your_spotify_client_id
SPOTIPY_CLIENT_SECRET=your_spotify_client_secret
FLASK_SECRET_KEY=replace-with-a-random-string
```

The `FLASK_SECRET_KEY` can be any random string (e.g., `python -c "import secrets; print(secrets.token_hex(32))"`).

### 3. Install Dependencies

```bash
# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# Install requirements
python -m pip install -r requirements.txt
```

**Dependencies**: Flask, Spotipy, python-dotenv, Requests

### 4. Run the Application

```bash
python app.py
```

Open your browser to `http://127.0.0.1:5000`

## Using the App

1. Click **Connect with Spotify** and authorize the following permissions:
   - `user-read-email` - Read your email address
   - `user-top-read` - Access your top artists and tracks
   - `user-library-read` - Read your saved tracks
   - `playlist-modify-public` - Create public playlists
   - `playlist-modify-private` - Create private playlists

2. Select your running cadence (140–190 BPM)

3. Click **Generate Playlist** and watch the real-time progress:
   - Fetching your music library
   - Discovering similar tracks
   - Analyzing track tempos
   - Building your playlist

4. Your playlist is created automatically and embedded on the page
   - Click **Open Playlist on Spotify** to view in the Spotify app
   - The playlist is private by default

## Technical Details

### Caching System

The app uses SQLite (`cache.db`) to store:
- User Spotify library data (30-day cache)
- ReccoBeats track recommendations (30-day cache)
- Track tempo/audio features (30-day cache)
- Tracks marked as unavailable on ReccoBeats (permanent, to avoid retry)

Cache benefits:
- Faster playlist generation on subsequent runs
- Reduced API calls to ReccoBeats
- Persistent across app restarts

### API Rate Limiting

- **Spotify API**: Managed automatically by Spotipy library
- **ReccoBeats API**: Batches requests (max 40 track IDs per call)
- Track IDs marked `fetch_status='no_data'` are skipped to avoid retries

### Tempo Filtering

The app filters tracks to a **10 BPM range** centered on your cadence:
- Target cadence: 170 BPM
- Filter range: 166–175 BPM (170 - 4 to 170 + 5)

This ensures tracks closely match your running rhythm while providing enough variety.

## Troubleshooting

**Missing credentials**
- Verify `.env` file exists and contains valid Spotify credentials
- Check that environment variables are loaded (restart the app)

**403/401 Authentication Errors**
- Confirm redirect URI is exactly `http://127.0.0.1:5000/callback` in Spotify dashboard
- Clear browser cookies and try logging in again
- Check that all required scopes are approved

**Empty or short playlist**
- The app needs diverse tracks near your target cadence
- Try a different cadence (170 BPM is typical for running)
- Add more music to your Spotify library
- The 10 BPM filter range is intentionally tight for better cadence matching

**Database Issues**
- Delete `cache.db` to reset all cached data
- The database will regenerate automatically

**Port Already in Use**
- Change the port in `app.py`: `app.run(debug=True, port=5001)`
- Update the redirect URI in Spotify dashboard and `.env` accordingly

## File Structure

```
spotify-flask-demo/
├── app.py                 # Main Flask application
├── cache.py              # SQLite caching layer
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables (create this)
├── cache.db             # SQLite database (auto-generated)
├── templates/
│   ├── base.html        # Base template with header/footer
│   └── index.html       # Main page (login + playlist generator)
└── static/
    └── style.css        # Modern dark theme styling
```

## Credits

Built with inspiration from **[Super Trainer](https://supertrainer.framer.website/)** - An AI coach that delivers personalized running guidance based on insights from top coaches.

---

Happy running! 🏃‍♀️🎵
