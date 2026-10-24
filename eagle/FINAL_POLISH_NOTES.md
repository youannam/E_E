# Eagle Eye UI polish notes

## Included in this package
- Kept the same Eagle Eye eagle/AI-cybersecurity icon SVG as the source of truth for the web favicon and mobile app icon; regenerated the Flutter PNG from that SVG so the two platforms use the same emblem.
- Adjusted Flutter dark-mode surfaces from near-black to charcoal gray, keeping the existing light white/baby-blue theme and the same risk colors.
- Left the API client, authentication flow, detection rules, AI model, risk scoring, database schema, and backend routes unchanged in this polish pass.

## Verification
- Focused backend/auth/risk/feature tests: `25 passed`.
- The full test suite and frontend dependency/build command did not finish within the available execution window; Flutter SDK availability/build was not verified here. Run the project checks locally before demo/deployment.

## Run checks
- Backend: `python -m pytest -q`
- Web: `cd frontend && npm install && npm run build`
- Flutter: `cd mobile && flutter pub get && flutter analyze`

The app is a controlled demonstration using synthetic activity; alerts should be investigated and are not proof of wrongdoing.
