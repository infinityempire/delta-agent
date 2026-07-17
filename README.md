# VocalizeBot PWA Shell

This repository hosts the static Progressive Web App shell that fronts the VocalizeBot deployment on GitHub Pages. The bundle focuses on proving that the `/VocalizeBot` scope can operate offline and advertises a basic health-check endpoint powered entirely by the service worker.

## Project layout
- `public/index.html` – main entry document that registers the service worker and exposes the offline ping control.
- `public/sw.js` – versioned service worker that precaches the static bundle and fulfils `/offline-ping` requests while offline.
- `public/manifest.webmanifest` – PWA metadata (icons, shortcuts, theme information).
- `public/404.html` – redirect helper so deep links resolve correctly on GitHub Pages.
- `src/` – placeholder for future framework-driven code.
- `.github/workflows/pages.yml` – deploys the `public/` directory to GitHub Pages from the `main` branch.
- `social_poster.py` – Delta Agent for broadcasting VocalizeBot marketing to social networks

## Running the bundle locally
1. Serve the `public/` directory with a static HTTP server so the service worker can register:
   ```bash
   npx http-server public -p 4173 -c-1
   ```
2. Visit <http://localhost:4173/VocalizeBot/>. The offline ping button should respond even if you toggle the browser to offline after the first load.

> ℹ️  The static server must respect the `/VocalizeBot` base path. The command above mirrors the GitHub Pages behaviour by serving the directory root and using cache-busting headers.

---

## 📱 Delta Agent - Social Media Broadcaster

The `social_poster.py` script broadcasts VocalizeBot marketing content to multiple social networks automatically.

### Quick Start (Termux)

```bash
# 1. Navigate to the agent directory
cd ~/delta-agent

# 2. Copy and configure .env
cp .env.example .env
nano .env    # Fill in your API keys

# 3. Install dependencies
pip install requests python-dotenv

# 4. Run the broadcaster
python3 social_poster.py

# Or broadcast to specific platforms only:
python3 social_poster.py telegram,mastodon
```

### Configuration (.env)

```bash
# 📱 Telegram (REQUIRED for group broadcasting)
TELEGRAM_BOT_TOKEN=your_bot_token_from_BotFather
TELEGRAM_CHAT_IDS=-1001234567890,-1009876543210  # Group IDs
TELEGRAM_DELAY_BETWEEN_POSTS=300  # 5 minutes between posts

# 🐘 Mastodon (Optional)
MASTODON_TOKEN=your_mastodon_access_token

# 🌀 Bluesky (Optional)
BLUESKY_HANDLE=your.bsky.social
BLUESKY_PASSWORD=your_app_password
```

### Supported Platforms

| Platform | Type | Status |
|----------|------|--------|
| 📱 Telegram | Groups | ✅ Ready |
| 🐘 Mastodon | Fediverse | ✅ Ready |
| 🌀 Bluesky | AT Protocol | ✅ Ready |
| ⚡ Nostr | Decentralized | ✅ Ready |
| 🦎 Lemmy | Forum | ✅ Ready |
| 📷 Threads | Meta | 🔜 Coming |
| 🌉 Farcaster | Web3 | 🔜 Coming |

### Anti-Spam Features

- Configurable delays between posts (default: 5 minutes)
- Rate limiting awareness
- Batch messaging with pauses

### Run in Background (Termux)

```bash
# Run with nohup
nohup python3 social_poster.py > broadcast.log 2>&1 &

# Check status
tail -f broadcast.log

# Or schedule with cron (run daily at 9 AM)
crontab -e
# Add: 0 9 * * * cd ~/delta-agent && python3 social_poster.py
```

---

## Deployment
The included workflow (`Deploy Pages PWA bundle`) validates that the critical files exist, uploads the `public/` directory as the Pages artefact, enables Pages for the repository, and then publishes from `main`. Any push to `main` automatically redeploys the site.

## Customising
- Update icons inside `public/` to reflect your branding. Keep both PNG sizes and the SVG for splash and favicon support.
- Extend the service worker in `public/sw.js` if you need additional offline routes. The `BASE_PATH` constant centralises the scoped path for convenience.
- Place future application code beneath `src/` and adjust the build tooling to emit the static artefacts back into `public/` before deployment.

---

# Triggering fresh deploy
