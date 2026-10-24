# User guide

For security analysts and administrators. Everything shown is synthetic demo data, marked with a
dashed **Simulated** tag and a notice at the top of every page.

## Logging in

Open the dashboard (http://localhost:5173) and log in with your Eagle Eye account. Your session
lasts 60 minutes; after that you are sent back to the login page with a message. After 5 wrong
passwords in 5 minutes, logins for that username are paused for a few minutes.

## Web dashboard

### Overview
* **Stat strip**: monitored users, active users (activity in the last 7 days), open alerts (and how
  many are being investigated), critical alerts still open, high-risk users, events in the last 24 hours.
* **Alerts per day**: the last 14 days, stacked by risk level, by the day the activity happened.
  Click a column to see that day's alerts.
* **Users by current risk** and **Activity by type** (last 7 days).
* **Recent alerts**: click a row to open it.

### Alerts
Filter by text (user or department), status, risk level, user and activity-day range; sort by
newest, highest risk, latest activity day or oldest. Fifteen alerts per page, with Previous/Next. "Clear filters" resets everything.

### Alert details (the investigation page)
* **Risk breakdown**: the big number is the final score. The bar shows the part from the
  cybersecurity rules (navy) and from the AI model (violet); a striped part means the
  critical-rule floor raised the score. The formula is written below the bar.
* **Cybersecurity rules**: each rule that fired, its severity, its points and the exact reason
  (with the user's own baseline numbers).
* **AI anomaly model**: the anomaly score, the model's verdict, the model version and which
  baseline type was used. Remember: the anomaly score is not a probability of guilt.
* **Explanation**: the same information as text, ready to copy into a report.
* **Evidence timeline**: the events that triggered the rules (or the day's events for AI-only alerts).
* **Investigation panel**: write a note, then
  * *Start investigating* → INVESTIGATING
  * *Mark resolved* / *Mark false positive* → requires a note explaining the decision
  * *Reopen* a closed alert
  * *Add note* (without changing the status), *Assign to me* / *Unassign*

  Status changes ask for confirmation. Everything is recorded in **Status history** with your
  name and the time.

### Users
All monitored users, sorted by current risk (highest daily risk in the last 7 days). Filter by
username, department or risk level. A user's page shows the 30-day risk chart (the dashed line is
the alert threshold; click a column with an alert to open it), the behavioral baseline (average and
usual variation per day, and whether it is the user's own, the department's or the default), the
30-day activity statistics and devices, previous alerts and recent activity.

### Activity log
Every received event, newest first, with filters for user, event type, sensitivity, source, date
range and resource/user text. Restricted resources are shown in bold crimson, confidential ones in orange.

### Simulation center (administrators)
1. Choose a scenario (A-H). Each card says what it generates and what to expect.
2. Choose the user, the day (default: yesterday), the random seed and the intensity (1-3). The same
   inputs always produce the same events.
3. *Run simulation*. The events are stored and analyzed by the real pipeline; the result shows the
   risk breakdown, the rules that fired, the AI score, whether an alert was raised (with a link)
   and the generated events.

Running a scenario again for the same user and day adds more events to that day; the day is
re-analyzed and its existing alert is updated rather than duplicated.

Analysts can see the scenarios, but the button is disabled for them.

### Detection rules
Shows the AI model in use (version, training time, synthetic test results) and the 8 rules.
Administrators can change a rule's weight and numeric thresholds (*Save settings*) or disable/enable
it; both ask for confirmation and apply to future analyses only.

## Mobile app (Flutter, Android)

* **Login**: username, password and server address (emulator: `http://10.0.2.2:8000`; phone: your
  computer's Wi-Fi address). The token is kept in the phone's encrypted storage.
* **Overview**: the same headline numbers as the web dashboard and the open alerts.
* **Alerts**: filter chips by status, pull down to refresh, *Load more* at the end.
* **Alert details**: score, rules and AI contributions, formula, triggered rules with reasons,
  AI verdict, explanation, evidence and history. Status buttons open a dialog with a note field
  (a note is required to resolve or mark as false positive).
* **Users**: users by current risk; tap one for the 30-day daily risk list (tap a day with a
  warning icon to open its alert).
* **Profile**: your account, role and server; *Log out* (with confirmation).

If the server cannot be reached, screens show an offline message with *Try again*.
