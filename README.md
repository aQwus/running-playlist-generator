# Running Playlist Generator

A Flask web application that generates Spotify running playlists matched to your cadence (steps per minute). The app uses your Spotify listening history and the ReccoBeats API to find tracks that match your running rhythm.

## Features

- **Spotify Integration**: OAuth authentication with automatic session management
- **Smart Track Selection**: Analyzes your top tracks, saved tracks, and discovers similar songs
- **Tempo Matching**: Finds tracks within your target cadence range (140–190 BPM)
- **Real-time Progress**: Live updates during playlist generation via Server-Sent Events
- **Intelligent Caching**: Uses a local SQLite database (`cache.db`) to store tempo data and recommendations for 30 days, reducing API calls and speeding up subsequent runs.
- **Modern UI**: Dark theme with responsive design inspired by athletic aesthetics
- **White-label Dropdown**: Accessible dropdown menus with high-contrast options

## How It Works

1. **Authentication**: Connects to your Spotify account with permissions for reading library and creating playlists
2. **Data Collection**: Gathers your top 50 tracks, recently saved tracks, and top artists' tracks.
3. **Expansion**: For each top track, fetches similar recommendations from ReccoBeats if your library is small.
4. **Tempo Analysis**: Retrieves tempo data via ReccoBeats API and caches it locally in `cache.db`.
5. **Filtering**: Selects tracks within your target cadence + 9 BPM (e.g., for 170 BPM, it finds 170-179 BPM).
6. **Playlist Creation**: Creates a private Spotify playlist named `Run Cadence <XXX> BPM`.

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
SPOTIFY_REDIRECT_URI=http://127.0.0.1:5000/callback
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

**Dependencies**: Flask, Spotipy, python-dotenv, Requests, Gunicorn

### 4. Run the Application

```bash
python app.py
```

Open your browser to `http://127.0.0.1:5000`

## Using the App

1. Click **Connect with Spotify** and authorize the required permissions.
2. Select your running cadence (140–190 BPM).
3. Click **Generate Playlist** and watch the real-time progress.
4. Your playlist is created automatically and embedded on the page.
   - Click **Open Playlist on Spotify** to view in the Spotify app.
   - The playlist is private by default.

## Technical Details

### Caching System

The app uses a local SQLite database (`cache.db`) which is **auto-generated** on the first run. It stores:
- User Spotify library data (30-day cache)
- ReccoBeats track recommendations (30-day cache)
- Track tempo/audio features (30-day cache)
- Tracks marked as unavailable on ReccoBeats (permanent, to avoid retry)

**Note:** `cache.db` is excluded from git to protect your local cache data.

### API Rate Limiting

- **Spotify API**: Managed automatically by Spotipy library
- **ReccoBeats API**: Batches requests (max 40 track IDs per call)

### Tempo Filtering

The app filters tracks to a **10 BPM range** starting from your cadence:
- Target cadence: 170 BPM
- Filter range: 170–179 BPM

This ensures tracks match your running rhythm while providing enough variety.

## Troubleshooting

**Missing credentials**
- Verify `.env` file exists and contains valid Spotify credentials.
- Check that environment variables are loaded (restart the app).

**403/401 Authentication Errors**
- Confirm redirect URI is exactly `http://127.0.0.1:5000/callback` in Spotify dashboard.
- Clear browser cookies and try logging in again.

**Database Issues**
- If you encounter strange caching behavior, you can safely delete the `cache.db` file. It will be recreated automatically on the next run.

## File Structure

```
spotify-flask-demo/
├── app.py                 # Main Flask application
├── cache.py               # SQLite caching layer
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (you create this)
├── .gitignore             # Git ignore rules
├── templates/
│   ├── base.html          # Base template with header/footer
│   └── index.html         # Main page (login + playlist generator)
└── static/
    └── style.css          # Modern dark theme styling
```

## Plug

Like this project? Check out **[Super Trainer](https://supertrainer.framer.website/)** - An AI coach that delivers personalized running guidance based on insights from top coaches. Hop on the waitlist to get notified at launch!

---

Happy running! 🏃‍♀️🎵
