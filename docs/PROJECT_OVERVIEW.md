# Project overview

## The problem

An *insider threat* is harm caused by someone who already has legitimate access: an employee
copying customer data before leaving, an account used at 2 a.m. by someone else, an
administrator deleting records. Firewalls and antivirus do not help much, because the
activity is done with valid credentials. What changes is **behavior**: more downloads than
usual, files outside the person's role, unusual hours, USB copies of sensitive data.

## What Eagle Eye does

1. **Collects activity events** (logins, file access, downloads, deletions, USB, e-mail, application use)
   through a REST API. In this project they come from a simulator.
2. **Summarizes each user's day** into 15 numeric features.
3. **Compares the day with the user's own history** (behavioral baseline).
4. **Checks 8 explicit cybersecurity rules** (e.g. "sensitive file copied to USB").
5. **Scores how unusual the day is** with an Isolation Forest model trained on normal days.
6. **Combines both** into a risk score 0-100 and a level (LOW, MEDIUM, HIGH, CRITICAL).
7. **Raises one alert per user-day** when the policy is met, with a plain-English explanation and
   the evidence events.
8. **Supports the investigation**: analysts change the status (OPEN, INVESTIGATING, RESOLVED,
   FALSE_POSITIVE), add notes and assign alerts; every change is recorded.
9. **Shows everything** in a web dashboard and an Android app that use the same API.

## Users of the system

| Role | Can do |
|---|---|
| Security analyst (`ANALYST`) | View everything; investigate and update alerts |
| Administrator (`ADMIN`) | Everything an analyst can, plus ingest activity, run the simulator, re-run analysis, change rule settings, register monitored users, reload the model |

Monitored employees never log in to Eagle Eye.

## Principles

* **An anomaly is not proof.** Every alert says so. The system never blocks, disables or punishes anyone;
  it only informs analysts.
* **Explainable decisions.** Each score is split into its rule part and AI part, each rule says
  why it fired, and the formula is shown.
* **Honesty about data.** All data is synthetic and labeled "simulated" in the UI. Reported metrics
  are computed by code on synthetic data and described as such.
* **Privacy by design.** Only work-activity metadata is processed (no message contents, no keystrokes,
  no screenshots). Monitored users have no passwords stored. Audit logs never contain secrets.
* **Defensive only.** No covert monitoring, credential collection or response actions.

## Scope

In scope: everything listed above, running locally on one machine for a demonstration.

Out of scope (see [LIMITATIONS.md](LIMITATIONS.md)): real log collectors (Windows events, DLP,
proxies), real employee data, push notifications, multi-server deployment, automatic responses.
