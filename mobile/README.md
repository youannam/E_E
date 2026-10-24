# Eagle Eye Flutter Console

The preserved Flutter console uses the same modular FastAPI database and detection pipeline as the web console through the compatibility adapter. The account login is an ADMIN or ANALYST account; monitored employees are separate records. Public account registration and self-service password reset are intentionally disabled.

## Windows one-command launch

From the project root, double-click `RUN_MOBILE.bat`. Choose Android Emulator, Windows Desktop, a physical Android phone over USB (recommended), or a phone on the same Wi-Fi. For USB, enable Developer options > USB debugging and accept the trust prompt; the launcher sets up `adb reverse` so the phone can reach the API even when it listens on localhost. The launcher can generate missing platform folders, allow local HTTP API traffic in the Android manifest, run `flutter pub get`, start the API if needed, and launch Flutter.

For Android Emulator, the API base is `http://10.0.2.2:8000`. For Windows Desktop it is `http://127.0.0.1:8000`. For a physical phone over USB, choose option 3; for Wi-Fi, choose option 4 and keep the PC and phone on the same trusted network.

## Manual launch

```bash
flutter create --platforms=android,windows --project-name eagle_eye_mobile .
flutter pub get
flutter run --dart-define=API_BASE=http://10.0.2.2:8000
```


## Role behavior

The mobile shell adapts its navigation to the signed-in role. Admins see Dashboard, Alerts, Monitored Users, Activity, and Detection Lab. Analysts see only Alerts and Detection Lab; they can investigate and resolve alerts and run synthetic scenarios, while the backend rejects admin-only requests. The Detection Lab calls the canonical `/api/v1/simulator/*` endpoints so generated events go through the real Rules + AI pipeline.
