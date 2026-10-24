# Demonstration script (about 12 minutes)

Everything runs locally; no internet, real company data or external security tools are needed.
The "observed" numbers come from our own run on 10 October 2026 (simulated day 2026-10-09, seed 42).
The simulated day is part of the random seed, so on another date the numbers differ somewhat; the
behavior (normal → LOW, combined → CRITICAL alert, benign → anomalous but no alert) is what to show.

## Before the presentation (10 minutes earlier)

```bash
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
python scripts/reset_demo.py              # fresh database + demo data; prints nothing secret
uvicorn backend.main:app --host 0.0.0.0 --port 8000
cd frontend && npm run dev                # second terminal
cd mobile && flutter run                  # third terminal, emulator already started
```

Open `demo_credentials.txt` for the passwords. Log in to the web dashboard as **admin** and to the
phone as **analyst**. Keep http://localhost:8000/docs open in a tab for questions about the API.

## Part A: normal behavior (2 min)

1. **Overview**: "25 synthetic employees, about a month of normal history. Every history day already
   went through the same pipeline; there are no alerts because nothing suspicious happened."
2. **Users → omar.hassan**: show the flat daily-risk chart and the **behavioral baseline** table:
   "Omar normally downloads about 3 files a day; this is his own baseline from his previous days."
3. **Simulation center**: scenario **A - Normal user**, user **mona.adel**, default day (yesterday),
   seed 42 → *Run simulation*.
   * Expect: LOW risk, no rules, "No alert". Observed: 15.9 LOW (rules 0, AI 26.5).
   * Point at the breakdown bar: "Even a normal day has a small AI score; it is far below 50."

## Part B: suspicious behavior (4 min)

4. Same page: scenario **G - Combined anomaly**, user **omar.hassan**, seed 42 → *Run simulation*.
   * Expect: CRITICAL, several rules, AI flags the day, an alert link.
     Observed: 91.8 CRITICAL = 0.4 × 100 (rules) + 0.6 × 86.4 (AI); six rules.
   * Scroll through the generated events: night login at about 01:30, restricted files, a download
     burst, USB copies, then his normal working day. All tagged **Simulated**.
5. Explain in one sentence each: rules = known bad patterns compared with *his* baseline;
   AI = "how unusual is this day compared with normal days"; risk = documented weighted formula;
   alert because the score is ≥ 50.
6. Optional contrast (1 min): scenario **H - Benign exception**, user **dina.khaled**.
   Observed: AI says anomalous (67.8) but no rule fires → 40.7 MEDIUM, **no alert**.
   "Unusual is not the same as malicious; that is why we combine signals and keep a human in the loop."
7. Optional personalization: scenario **B - Unusual login** for **khaled.ramy** (night-shift technician):
   the night-login rule does **not** fire because his baseline contains night logins.

## Part C: investigation (3 min)

8. Click the alert link (or **Alerts** → the CRITICAL alert for omar.hassan).
9. Walk through the page top-down: breakdown bar and formula, each rule's reason with numbers from his
   baseline, the AI box ("not a probability of guilt"), the explanation text, the evidence timeline.
10. Type a note ("Contacting line manager"), click **Start investigating**, confirm.
    The status history shows the change with your name and time.
11. Switch to the **phone**: Alerts tab → filter *Investigating* → the same alert, same score and rules.
    Open it, add a note via **Resolved** (a note is required), save.
12. Back on the web, reload the alert: status RESOLVED, the phone's note in the history.
    "The backend is the single source of truth; both clients only display it."

## Part D: under the hood (2 min, if asked)

* **Detection rules** page: model version, synthetic test results, rule weights and thresholds
  (admin can change them, with confirmation and audit).
* Swagger `/docs`: the same endpoints the clients use; try `GET /api/v1/alerts` without a token → 401.
* Terminal: `pytest` (85 tests) or `python -m scripts.evaluate_detection` for the whole-system numbers.
* Terminal: `python -m simulator.cli --scenario USB_TRANSFER --username heba.yasser` shows how an
  external log collector would send events over HTTP.

## If something goes wrong

| Problem | Quick fix |
|---|---|
| A scenario was already run for that user and day (scores higher than expected) | Pick another user or another day, or run `python scripts/reset_demo.py` |
| "AI model not loaded" on the overview | `python -m ai.train`, then restart the API |
| Phone cannot connect | Check the server address on the login screen and that the API runs with `--host 0.0.0.0` |
| Browser shows "Cannot reach the Eagle Eye API" | The API terminal stopped; restart `uvicorn` |
