# BeatScout

**Discover → Clear → Render → Publish.** An autonomous, rights-first pipeline that finds low-exposure indie music, clears usage rights, generates audio-reactive YouTube visualizers, and publishes them — with every step logged, queued, and auditable.

BeatScout is built to run end-to-end with **zero credentials** (mock Spotify + mock YouTube providers) so the whole pipeline is testable offline, and to swap in real credentials when you have them.

---

## The funnel

| Stage | What happens | Legal guard |
|---|---|---|
| 1. Discover | Metadata-only search for low-exposure, unclaimed tracks (Spotify or mock provider). **No audio is downloaded.** | Scoring promotes only low-exposure artists (freshness ≥ 0, max exposure cap per genre window) |
| 2. Clear | Request permission from the artist; attach a license or artist-provided audio; verify license terms | **Render is blocked unless the track is `APPROVED`** (`require_approved_rights` gate in `app/services/video`) |
| 3. Render | Audio-reactive visualizer MP4 (5 styles) + branded 1280×720 thumbnail + legal metadata | Metadata generator never claims "official release" — disclosure line is appended to every description |
| 4. Publish | YouTube upload (private by default) with license notes in the description | Upload metadata is generated from the verified license record |

Everything runs through a **run-to-completion job queue** (`discover → analyze → render → publish`): in-process worker for local/dev, Celery when `REDIS_URL` is set.

---

## Quick start (dev, no Docker)

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows; use .venv/bin on POSIX
env -u PYTHONPATH .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

On first boot the app seeds a **demo user** and 24 mock tracks:

- **email** `demo@beatscout.app` · **password** `demo1234`
- 2 of the 24 tracks are pre-`APPROVED` with a demo render + thumbnail, so the studio and YouTube pages work immediately.

```bash
# Frontend
cd frontend
npm install
npm run dev          # http://localhost:5173 (proxies /api and /media to :8000)
```

### Docker (single command)

```bash
docker compose up --build
# Backend API  -> http://localhost:8000  (docs at /docs)
# Frontend     -> http://localhost:8080
```

## Tests

```bash
cd backend
env -u PYTHONPATH .venv/Scripts/python.exe -m pytest    # 29 tests, all offline
cd ../frontend && npm run build                          # TS strict + Vite bundle
```

---

## API surface (all under `/api`, JWT-secured)

| Router | Endpoints |
|---|---|
| `auth` | `POST /register`, `POST /login`, `GET /me` |
| `spotify` | `GET /status`, `GET /genres`, `POST /discover` |
| `tracks` | `GET /`, `POST /{id}/reject` |
| `rights` | `POST /tracks/{id}/permission`, `POST /permissions/{id}/approve`, `POST /tracks/{id}/audio`, `POST /tracks/{id}/license/verify` |
| `videos` | `GET /templates`, `POST /generate`, `GET /` |
| `youtube` | `GET /status`, `POST /connect`, `POST /upload`, `GET /uploads`, `GET /channel` |
| `automation` | `POST /create`, `PATCH /{id}`, `POST /{id}/run`, `GET /` |
| `jobs` | `GET /`, `POST /`, `POST /{type}/enqueue`, `POST /{id}/cancel`, `POST /{id}/retry` |
| `dashboard` | `GET /` (funnel stats + provider mode) |

Interactive docs: `http://localhost:8000/docs`.

## Configuration (`.env` or environment)

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | dev value | JWT signing — **set in production** |
| `DATABASE_URL` | `sqlite:///./beatscout.db` | Postgres: `postgresql+psycopg://…` |
| `SEED_DEMO` | `1` | demo user + tracks on first boot |
| `AUTO_RUN_WORKER` | `1` | in-process job worker (0 + `REDIS_URL` → Celery) |
| `REDIS_URL` | empty | set to enable the Celery worker |
| `RATE_LIMIT_ENABLED` | `1` | per-route rate limiting |
| `SPOTIFY_CLIENT_ID/SECRET` | empty → mock | real discovery when set |
| `YOUTUBE_CLIENT_ID/SECRET/REDIRECT_URI` | empty → mock | real publishing when set |
| `STORAGE_DIR` | `./storage` | artwork / audio / video / thumbnails (served under `/media`) |

## Project layout

```
backend/
  app/
    api/            # routers: auth, spotify, tracks, rights, videos, youtube, automation, jobs, dashboard
    models/         # SQLAlchemy: User, Artist, Track, Permission, License, Video, YouTube*, Automation, Job
    schemas/        # pydantic request/response models
    services/
      spotify/      # provider factory: MockSpotifyProvider | RealSpotifyProvider
      discovery/    # scoring rubric + persistence
      rights/       # permission life cycle + APPROVED gate
      audio/        # ingestion (ext allowlist), analysis (numpy FFT engine, librosa optional)
      video/        # engine (5 templates), prep, thumbnail, metadata generator, render service
      youtube/      # provider factory: mock uploads | real OAuth2 uploads
      jobs/         # durable job table + in-process worker + Celery entrypoint
      seed.py       # demo data
  tests/            # 29 pytest tests
frontend/
  src/
    components/     # shadcn-style UI kit, Layout, Logo
    pages/          # Login, Register, Dashboard, Discovery, Tracks, Studio, Youtube, Automations, Jobs
    api.ts          # typed fetch client + media URL resolver
Dockerfile · docker-compose.yml · .env.example
```

## Autonomous daily pipeline (GitHub Actions)

`app/auto.py` (+ `.github/workflows/daily-5-videos.yml`) runs the whole loop
headless every day at 05:30 UTC: **discover → license-check → download →
render → publish**, 5 videos per run, no UI, no human in the loop.

- **Source**: the [Jamendo](https://developer.jamendo.com) free API — every
  track carries an explicit Creative-Commons license. Only `by` / `by-sa` /
  `zero` (commercial + derivative OK) are auto-published; everything else
  stays in the human-review app. This is the same legal gate as the render
  service, but grantable without a round-trip.
- **Dedupe**: `auto-state/auto_state.json` is committed back to the repo after
  each run, so no track is ever published twice.
- **Zero-secret CI**: with no secrets configured the run renders and logs
  (dry-run) and still passes — the pipeline is provably alive before any key
  exists. With secrets it publishes for real.

To go live you need **4 GitHub secrets** (one-time ≈ 10 minutes):

| Secret | How to get it |
|---|---|
| `JAMENDO_CLIENT_ID` | free API key at developer.jamendo.com (`Create client id`) |
| `YOUTUBE_CLIENT_ID` | Google Cloud → OAuth client (Desktop) → YouTube Data API v3 enabled |
| `YOUTUBE_CLIENT_SECRET` | same OAuth client |
| `YOUTUBE_REFRESH_TOKEN` | run `backend/scripts/yt_token.py` once, paste the printed token (scope: youtube.upload) |

Then re-run the workflow with `dry_run: 0`. Titles/descriptions carry the
license + artist credit automatically. Size/FPS are tuned for CI
(480p, 60s clip, 24fps); bump `VIDEO_WIDTH/HEIGHT/FPS` envs for desk rendering.

```bash
# run the same thing locally (no keys needed — synth provider, dry run)
cd backend && env -u PYTHONPATH ./.venv/Scripts/python.exe -m app.auto --limit 5
```

## License note

BeatScout is a **rights-clearance pipeline**, not a content-stealer: the render service hard-fails on tracks without an approved permission or verified license, and the YouTube metadata generator appends the disclosure _"Not an official release — visualizer made with the track owner's permission."_ Real Spotify/YouTube credentials are optional; with none, both providers run fully in mock mode.