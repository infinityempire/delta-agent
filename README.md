# Infinity Agent PWA Shell

This repository hosts the static Progressive Web App shell that fronts the Infinity Agent deployment on GitHub Pages. The bundle focuses on proving that the `/Infinity-agent` scope can operate offline and advertises a basic health-check endpoint powered entirely by the service worker.

## Project layout
- `public/index.html` – main entry document that registers the service worker and exposes the offline ping control.
- `public/sw.js` – versioned service worker that precaches the static bundle and fulfils `/offline-ping` requests while offline.
- `public/manifest.webmanifest` – PWA metadata (icons, shortcuts, theme information).
- `public/404.html` – redirect helper so deep links resolve correctly on GitHub Pages.
- `src/` – placeholder for future framework-driven code.
- `.github/workflows/pages.yml` – deploys the `public/` directory to GitHub Pages from the `main` branch.

## Running the bundle locally
1. Serve the `public/` directory with a static HTTP server so the service worker can register:
   ```bash
   npx http-server public -p 4173 -c-1
   ```
2. Visit <http://localhost:4173/Infinity-agent/>. The offline ping button should respond even if you toggle the browser to offline after the first load.

> ℹ️  The static server must respect the `/Infinity-agent` base path. The command above mirrors the GitHub Pages behaviour by serving the directory root and using cache-busting headers.

## Deployment
The included workflow (`Deploy Pages PWA bundle`) validates that the critical files exist, uploads the `public/` directory as the Pages artefact, enables Pages for the repository, and then publishes from `main`. Any push to `main` automatically redeploys the site.

## Customising
- Update icons inside `public/` to reflect your branding. Keep both PNG sizes and the SVG for splash and favicon support.
- Extend the service worker in `public/sw.js` if you need additional offline routes. The `BASE_PATH` constant centralises the scoped path for convenience.
- Place future application code beneath `src/` and adjust the build tooling to emit the static artefacts back into `public/` before deployment.

---

# Triggering fresh deploy
