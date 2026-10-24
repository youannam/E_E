# Eagle Eye web dashboard

React 19 + TypeScript + Vite. All data comes from the Eagle Eye API; nothing is calculated here.

```bash
npm install
cp .env.example .env.local     # optional: change VITE_API_BASE_URL (default http://localhost:8000)
npm run dev                    # http://localhost:5173
npm test                       # unit tests of the helpers (Node test runner via tsx)
npm run build                  # type-check + production build into dist/
npm run preview                # serve the build on http://localhost:4173 (add it to CORS_ORIGINS)
```

Structure: `src/api` (HTTP client, types, `useApi` hook), `src/auth` (login state),
`src/components` (badges, tables helpers, risk breakdown, charts, dialog, layout),
`src/pages` (one file per screen), `src/utils` (formatting and hash routing), `src/styles.css`.

Design notes: light, high-contrast theme for projectors; system fonts so it works offline;
one fixed four-color risk scale used everywhere; charts are small SVG/HTML components instead of a
chart library. Browser tests: `RUN_E2E=1 pytest tests/e2e` from the project root.
